import json
import time
import asyncio
import httpx
import re
from typing import Dict, Any, List, Optional

# Models that returned 429 are skipped until this monotonic timestamp, so a batch
# doesn't spend a round trip per product on a model that is rate-limited upstream.
_MODEL_COOLDOWN_UNTIL: Dict[str, float] = {}
DEFAULT_RATE_LIMIT_COOLDOWN_S = 60.0
MAX_RATE_LIMIT_COOLDOWN_S = 600.0
# A 429 asking us to wait this long or less is waited out once instead of skipping the model
MAX_INLINE_RATE_LIMIT_WAIT_S = 10.0
# When every model is cooling down, wait for the first to free up (free tiers reset per minute)
# rather than writing template copy, up to this long per wait and this many waits per listing
MAX_COOLDOWN_WAIT_S = 75.0
MAX_COOLDOWN_WAIT_ROUNDS = 3

# Marks content written by the built-in generator rather than an AI model
TEMPLATE_ENGINE = "category_agnostic_rule_engine"

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
# Tried after GROQ_MODEL, in order, before the built-in generator
GROQ_FALLBACK_MODELS = ["qwen/qwen3.8-27b", "openai/gpt-oss-20b"]
# gpt-oss models reason before answering; "low" halves output tokens (stretches free-tier
# per-minute limits) with no loss in listing quality. Other models reject the parameter.
GROQ_REASONING_EFFORT_PREFIX = "openai/gpt-oss"
from app.core.config import settings
from app.models.product import Product
from app.services.settings_service import SettingsService
from app.services.amazon_ptd_service import AmazonPTDService
from app.services.meesho_adapter import MeeshoAdapter, MEESHO_FLAGGED_WORDS, MEESHO_CATEGORY_ATTR
from app.services.marketplace_limits import title_limit, keyword_byte_limit, prompt_target
from app.services.rule_engine import RuleEngine

# Meesho copy that fails the deterministic checks (RuleEngine.meesho_copy_issues) is regenerated with
# the failures listed, at most this many times; what's left then shows as errors to fix before approval
MEESHO_COPY_RETRIES = 2

# Meesho copy is plain catalogue text for phone shoppers: facts from the product data, search terms in
# the title and description (Meesho has no keyword field), nothing the template or QC rejects
MEESHO_PROMPT_SYSTEM = """You write Meesho catalogue listings for ListingPilot from a seller's own product data.
Meesho shoppers browse on phones and search in simple words, often Hinglish. Meesho has no keyword field, so the title and description must carry the words shoppers search for.

Brand: {brand}
Tone: {tone}. Plain, factual and easy to read.
Guidance & Avoidance: {avoid_claims}

Facts:
- Use ONLY the facts in the product data: its name, category, attributes and notes. Every material, colour, pattern, size, count, use and feature you write must be stated there.
- Write numbers and measurements exactly as the data gives them. Never convert units, round or add a number.
- Never write "100%", "pure", "genuine", "handmade", washing instructions, certifications, warranty or any other claim unless the data states it in those words.
- No praise words such as premium, luxury, durable, best, high quality or perfect.
- No offers or policy claims such as free delivery, best seller, cheapest or money back.

Listing:
1. Title: At most {title_chars} characters including spaces. The brand if one is given, the product type in the words shoppers search for, then two or three stated attributes that tell this product apart (colour, material, pattern, audience, pack count). No size, weight, dimension, price or marketplace name. Normal capitalisation, never all caps.
2. Bullets: 3 to 5 short bullets. Each starts with a short capitalised headline and an em dash, and states one fact from the data. Leave a bullet out rather than pad it.
3. Description: 2 to 4 short plain-text sentences (no HTML, no lists) that restate the stated facts and name the product type the way shoppers search for it, including the Hindi or Hinglish name Indian shoppers commonly type for this product type if there is one.
4. Keywords: 5 to 8 search phrases shoppers type for this exact product, built from its product type and stated attributes, including Hinglish ones. All keywords together must fit within {keyword_bytes} bytes (UTF-8).

Output must be STRICTLY valid JSON with no conversational text or markdown code fences:
{{"title": "...", "bullets": ["...", "..."], "description": "...", "keywords": ["...", "..."]}}"""

PROMPT_SYSTEM = """You are ListingPilot's marketplace listing generation engine. 
Your role is to transform raw master catalogue product data into high-converting, compliant, exhaustive tier-1 listings (Apple / flagship merchant caliber) for Amazon.in, Flipkart, and Meesho.
ListingPilot is strictly CATEGORY AGNOSTIC and supports ANY sellable product category (e.g., electronics, apparel, footwear, home & kitchen, beauty, tools, grocery, decor, toys, jewelry, etc.).

Brand: {brand}
Brand Voice & Guidelines:
- Tone: {tone}
- Target Audience: {audience}
- Guidance & Avoidance: {avoid_claims}
- Quality: World-class, benefit-driven specifications and narrative storytelling.
- Accuracy: Use ONLY the provided product attributes and specs. Never fabricate dimensions, materials, or certifications.

Strict Marketplace Rules:
1. Title: At most {title_chars} characters including spaces. Formula: [Brand] + [Product Type / Key Attributes] + [Material / Model / Size / Colour] + [Use / Benefit]. Do not use all-caps for entire words.
2. 5 Bullet Points: Exactly 5 bullets. Start each bullet with a short capitalized headline followed by an em-dash or colon (e.g., "CORE PERFORMANCE — ..."). Focus on: (1) Primary Breakthrough / Core Benefit, (2) Material & Build Quality, (3) Dimensions, Capacity & Fit, (4) Everyday Versatility & Inclusions, (5) Care Instructions & Longevity.
3. Description: 2-3 concise paragraphs highlighting core utility, build quality, and everyday benefits.
4. Keywords: 5 to 8 relevant search phrases shoppers actually search for. All keywords together must fit within {keyword_bytes} bytes (UTF-8).
5. Technical Specs: Structured dictionary for Amazon's Technical Details table with ONLY the specifications stated in the product attributes. Leave out anything they don't state; never add warranty, weight, country of origin, manufacturer or certifications that weren't provided.
6. A+ Enhanced Brand Content: Include hero headline, inspiring brand story, 3 feature spotlight cards (title, subtitle, description), and a comparison table matrix comparing this model with alternatives.
7. PROHIBITED: NEVER include promotional or policy claims like "Free delivery", "Best seller", "100% guarantee", "Cheapest", "Money back".

Output must be STRICTLY valid JSON with no conversational text or markdown code fences:
{{
  "title": "...",
  "bullets": ["...", "...", "...", "...", "..."],
  "description": "...",
  "keywords": ["...", "..."],
  "technical_specs": {{
    "Specification Key": "Value"
  }},
  "aplus_content": {{
    "headline": "...",
    "brand_story": "...",
    "feature_cards": [
      {{"title": "...", "subtitle": "...", "description": "..."}},
      {{"title": "...", "subtitle": "...", "description": "..."}},
      {{"title": "...", "subtitle": "...", "description": "..."}}
    ],
    "comparison_table": {{
      "headers": ["Specification", "This Model", "Standard Market Alternative", "Pro / Luxury Edition"],
      "rows": [
        {{"feature": "...", "this_model": "...", "standard": "...", "pro": "..."}}
      ]
    }}
  }}
}}"""

class AIService:
    """Generates marketplace listings using OpenRouter (free/low-cost) or Anthropic Claude API."""

    @staticmethod
    def generation_source(content: Dict[str, Any]) -> str:
        """'template' when the built-in generator wrote the content, 'ai' when a model did."""
        return "template" if content.get("engine") == TEMPLATE_ENGINE else "ai"

    @classmethod
    async def generate_listing(cls, product: Product, marketplace: str = "amazon") -> Dict[str, Any]:
        voice = SettingsService.get_brand_voice()
        brand = product.brand or voice.get("brand_name") or settings.DEFAULT_BRAND
        tone = voice.get("tone", "Professional, benefit-driven, informative, and engaging")
        audience = voice.get("target_audience", "Discerning shoppers seeking premium quality, reliability, and value")
        avoid_claims = voice.get("avoid_claims", "Avoid cheap promotional slang, fake certifications, or unverified claims")

        if marketplace.lower() == "meesho":
            return await cls._generate_meesho(product, brand, tone, avoid_claims)

        system_prompt = PROMPT_SYSTEM.format(
            brand=brand,
            tone=tone,
            audience=audience,
            avoid_claims=avoid_claims,
            title_chars=prompt_target(title_limit(marketplace)),
            keyword_bytes=prompt_target(keyword_byte_limit(marketplace)),
        )
        
        attrs_str = ", ".join([f"{k}: {v}" for k, v in (product.attributes or {}).items()])
        ptd_guidance = AmazonPTDService.get_category_prompt_guidance(product.category or "", product.name or "")
        user_prompt = f"""Generate a {marketplace.upper()} listing for:
SKU: {product.sku}
Product Name: {product.name}
Category: {product.category}
Brand: {brand}
Selling Price: ₹{product.price}
Specs & Attributes: {attrs_str if attrs_str else 'none provided (do not invent any)'}
Notes: {product.description or ''}
Target Marketplace: {marketplace.upper()}

Category Schema Guidelines (Amazon SP-API PTD):
{ptd_guidance}"""
        return await cls._generate(system_prompt, user_prompt, product, marketplace, brand)

    @classmethod
    async def _generate_meesho(cls, product: Product, brand: str, tone: str, avoid_claims: str) -> Dict[str, Any]:
        """
        Meesho copy from the product's data and its Meesho template (category path and the fields shoppers
        filter by). Copy failing the deterministic checks (invented facts, flagged words, Product Name
        rules, length) is regenerated with the failures listed, up to MEESHO_COPY_RETRIES times.
        """
        tmpl, _ = MeeshoAdapter.resolve_item_template({"product": product})
        system_prompt = MEESHO_PROMPT_SYSTEM.format(
            brand=brand,
            tone=tone,
            avoid_claims=avoid_claims,
            title_chars=prompt_target(title_limit("meesho")),
            keyword_bytes=prompt_target(keyword_byte_limit("meesho")),
        )
        attrs = [f"- {k}: {v}" for k, v in (product.attributes or {}).items()
                 if v is not None and str(v).strip() and str(k).strip().lower() != MEESHO_CATEGORY_ATTR.lower()]
        filters = MeeshoAdapter.filter_fields(tmpl)
        flagged = ", ".join(f"'{w}'" for w in MEESHO_FLAGGED_WORDS)
        user_prompt = f"""Write the Meesho listing for:
SKU: {product.sku}
Product Name: {product.name}
Seller's category: {product.category}
Meesho category: {tmpl["breadcrumb"] if tmpl else "not chosen yet"}
Brand: {brand}
Attributes:
{chr(10).join(attrs) if attrs else "- none provided (do not invent any)"}
Notes: {product.description or ''}
""" + (f"Shoppers filter this Meesho category by: {', '.join(filters)}. Mention the ones the attributes state.\n" if filters else "") + f"""
Meesho rules:
- Meesho's catalogue check flags the words {flagged} in listing text. Do not use them in any form.
- If the data states washing or maintenance, head that bullet "WASH & MAINTENANCE", never "CARE INSTRUCTIONS".
- Every product needs its own title; tell this product apart by its own stated design, colour and material."""

        content = await cls._generate(system_prompt, user_prompt, product, "meesho", brand)
        for attempt in range(1, MEESHO_COPY_RETRIES + 1):
            if cls.generation_source(content) == "template":
                break
            errors = [i["message"] for i in RuleEngine.meesho_copy_issues(product, content) if i["level"] == "error"]
            if len(content.get("title") or "") > title_limit("meesho"):
                errors.append(f"The title is {len(content['title'])} characters; Meesho allows {title_limit('meesho')}.")
            if not errors:
                break
            print(f"[AIService] {product.sku}: Meesho copy failed {len(errors)} check(s); regenerating "
                  f"({attempt}/{MEESHO_COPY_RETRIES})", flush=True)
            retry_prompt = (user_prompt + "\n\nYour previous listing broke these rules:\n"
                            + "\n".join(f"- {e}" for e in errors)
                            + "\nWrite the whole listing again without these problems, using only the product data above.")
            content = await cls._generate(system_prompt, retry_prompt, product, "meesho", brand)
        return content

    @classmethod
    async def _generate(cls, system_prompt: str, user_prompt: str, product: Product, marketplace: str, brand: str) -> Dict[str, Any]:
        """One listing from the configured provider (template copy when none is configured)."""
        # Check configured provider or dynamic settings credentials
        raw_creds = SettingsService.get_raw_settings().get("credentials", {})
        saved_key = (raw_creds.get("openrouter_api_key") or "").strip()
        
        # Guard against dummy or masked placeholders (e.g. sk-or-v1-abcdef... or sk-****)
        if saved_key and not saved_key.startswith("sk-or-v1-abcdef") and "*" not in saved_key:
            openrouter_key = saved_key
        else:
            openrouter_key = getattr(settings, "OPENROUTER_API_KEY", "")

        if settings.AI_PROVIDER == "groq":
            return await cls._call_groq(system_prompt, user_prompt, product, marketplace=marketplace)
        if settings.AI_PROVIDER == "openrouter" or (openrouter_key and not settings.ANTHROPIC_API_KEY):
            return await cls._call_openrouter(system_prompt, user_prompt, product, marketplace=marketplace, custom_key=openrouter_key)
        elif settings.ANTHROPIC_API_KEY:
            return await cls._call_anthropic(system_prompt, user_prompt, product, marketplace=marketplace)
        else:
            # Fallback to high-fidelity template generation if API key is not yet provided
            return cls._fallback_generator(product, brand, marketplace=marketplace)

    @classmethod
    async def _call_openrouter(cls, system_prompt: str, user_prompt: str, product: Product, marketplace: str = "amazon", custom_key: Optional[str] = None) -> Dict[str, Any]:
        api_key = custom_key or settings.OPENROUTER_API_KEY
        if not api_key:
            print("No OpenRouter API key found; using fallback generator")
            return cls._fallback_generator(product, product.brand or settings.DEFAULT_BRAND, marketplace=marketplace)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://listingpilot.local",
            "X-Title": "ListingPilot",
            "Content-Type": "application/json"
        }
        
        configured_model = settings.OPENROUTER_MODEL or "minimax/minimax-m3.1-flash"
        # Sanitize retired :free suffix if still present in environment
        if configured_model and "minimax/minimax-m3.1-flash:free" in configured_model:
            configured_model = "minimax/minimax-m3.1-flash"

        candidate_models = [
            configured_model,
            # Regular (non-:free) Google models are routed through our own Google AI Studio
            # key via OpenRouter BYOK, so they use our quota instead of the shared free pool
            "google/gemma-4-26b-a4b-it",
            "google/gemini-3.5-flash-lite",
            "google/gemma-4-26b-a4b-it:free",
            "nvidia/nemotron-3.5-lightning:free",
            "minimax/minimax-m3.1-flash",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "google/gemma-4-31b-it:free",
            "liquid/lfm-2.5-2.6b:free",
            "recursive/flint-v1.0:free",
            # OpenRouter's auto-router: picks whichever free model is currently available
            "openrouter/free"
        ]
        # Remove duplicates while preserving order
        models_to_try = []
        for m in candidate_models:
            if m and m not in models_to_try:
                models_to_try.append(m)

        return await cls._call_chat_completions(
            "OpenRouter", OPENROUTER_CHAT_URL, headers, models_to_try,
            system_prompt, user_prompt, product, marketplace=marketplace,
        )

    @classmethod
    async def _call_groq(cls, system_prompt: str, user_prompt: str, product: Product, marketplace: str = "amazon") -> Dict[str, Any]:
        """Calls Groq's OpenAI-compatible API directly (free tier; no OpenRouter credits involved)."""
        if not settings.GROQ_API_KEY:
            print("Groq: GROQ_API_KEY is not set; using built-in generator", flush=True)
            return cls._fallback_generator(product, product.brand or settings.DEFAULT_BRAND, marketplace=marketplace)

        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        models_to_try = []
        for m in [settings.GROQ_MODEL, *GROQ_FALLBACK_MODELS]:
            if m and m not in models_to_try:
                models_to_try.append(m)

        return await cls._call_chat_completions(
            "Groq", GROQ_CHAT_URL, headers, models_to_try,
            system_prompt, user_prompt, product, marketplace=marketplace,
            # JSON mode: Groq guarantees a syntactically valid JSON object
            extra_payload={"response_format": {"type": "json_object"}},
            per_model_payload={
                m: {"reasoning_effort": "low"} for m in models_to_try if m.startswith(GROQ_REASONING_EFFORT_PREFIX)
            },
        )

    @classmethod
    async def _call_chat_completions(
        cls,
        provider: str,
        url: str,
        headers: Dict[str, str],
        models_to_try: List[str],
        system_prompt: str,
        user_prompt: str,
        product: Product,
        marketplace: str = "amazon",
        extra_payload: Optional[Dict[str, Any]] = None,
        per_model_payload: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Tries each model on an OpenAI-compatible chat completions endpoint until one returns
        a parseable listing. Rate-limited models are skipped (or briefly waited on). When every
        model is cooling down and the first frees up within MAX_COOLDOWN_WAIT_S, waits for it
        instead of writing template copy; otherwise falls back to the built-in generator.
        """
        async with httpx.AsyncClient(timeout=22.0) as client:
            for wait_round in range(MAX_COOLDOWN_WAIT_ROUNDS + 1):
                now = time.monotonic()
                available_models = [m for m in models_to_try if _MODEL_COOLDOWN_UNTIL.get(m, 0) <= now]
                parsed = await cls._try_models(
                    client, provider, url, headers, available_models, system_prompt, user_prompt,
                    product, marketplace, extra_payload, per_model_payload,
                )
                if parsed:
                    return parsed

                # Only rate limits are worth waiting out; other failures won't fix themselves
                cooldowns = [_MODEL_COOLDOWN_UNTIL[m] for m in models_to_try if _MODEL_COOLDOWN_UNTIL.get(m, 0) > time.monotonic()]
                if not cooldowns or wait_round == MAX_COOLDOWN_WAIT_ROUNDS:
                    break
                wait_s = min(cooldowns) - time.monotonic()
                if wait_s > MAX_COOLDOWN_WAIT_S:
                    break
                print(f"{provider}: all models rate-limited; waiting {wait_s:.0f}s for the first to free up", flush=True)
                await asyncio.sleep(max(wait_s, 0.0))

        print(f"{provider}: no model produced a listing; generating template copy via built-in rule engine", flush=True)
        return cls._fallback_generator(product, product.brand or settings.DEFAULT_BRAND, marketplace=marketplace)

    @classmethod
    async def _try_models(
        cls,
        client: httpx.AsyncClient,
        provider: str,
        url: str,
        headers: Dict[str, str],
        available_models: List[str],
        system_prompt: str,
        user_prompt: str,
        product: Product,
        marketplace: str,
        extra_payload: Optional[Dict[str, Any]],
        per_model_payload: Optional[Dict[str, Dict[str, Any]]],
    ) -> Optional[Dict[str, Any]]:
        """One pass over the available models; returns the first parsed listing, or None."""
        for model_name in available_models:
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 3000,
                **(extra_payload or {}),
                **(per_model_payload or {}).get(model_name, {}),
            }

            try:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 429:
                    cooldown = cls._rate_limit_cooldown(res)
                    if cooldown <= MAX_INLINE_RATE_LIMIT_WAIT_S:
                        # Per-minute limits (e.g. Groq free tier) clear in seconds: wait once and retry
                        print(f"{provider}: {model_name} rate-limited (429); retrying in {cooldown:.1f}s", flush=True)
                        await asyncio.sleep(cooldown)
                        res = await client.post(url, headers=headers, json=payload)
                    if res.status_code == 429:
                        cooldown = cls._rate_limit_cooldown(res)
                        _MODEL_COOLDOWN_UNTIL[model_name] = time.monotonic() + cooldown
                        print(f"{provider}: {model_name} rate-limited (429); skipping it for {int(cooldown)}s", flush=True)
                        continue
                res.raise_for_status()
                data = res.json()
                choices = data.get("choices", [])
                if not choices or "message" not in choices[0]:
                    print(f"{provider}: {model_name} returned no choices; trying next model", flush=True)
                    continue
                msg = choices[0]["message"]
                content = msg.get("content")
                # Handle reasoning models where output or JSON was generated in reasoning
                if not content and msg.get("reasoning"):
                    reasoning_text = msg["reasoning"]
                    json_match = re.search(r"(\{\s*\"title\".*\})", reasoning_text, flags=re.DOTALL)
                    if json_match:
                        content = json_match.group(1)
                if not content or not isinstance(content, str) or not content.strip():
                    print(f"{provider}: {model_name} returned empty content; trying next model", flush=True)
                    continue
                parsed = cls._parse_json_response(content, product, marketplace=marketplace, fallback_on_error=False)
                if parsed and parsed.get("title"):
                    return parsed
                print(f"{provider}: {model_name} returned unparseable JSON; trying next model", flush=True)
            except httpx.HTTPStatusError as e:
                print(f"{provider}: {model_name} HTTP {e.response.status_code}: {e.response.text[:200]}", flush=True)
            except httpx.RequestError as e:
                print(f"{provider}: {model_name} network error: {e}", flush=True)
            except Exception as e:
                print(f"{provider}: {model_name} processing error: {e}", flush=True)

        return None

    @classmethod
    async def _call_anthropic(cls, system_prompt: str, user_prompt: str, product: Product, marketplace: str = "amazon") -> Dict[str, Any]:
        api_key = settings.ANTHROPIC_API_KEY
        if not api_key:
            return cls._fallback_generator(product, product.brand or settings.DEFAULT_BRAND, marketplace=marketplace)

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        payload = {
            "model": settings.CLAUDE_MODEL,
            "max_tokens": 1500,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt}
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                res = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
                res.raise_for_status()
                data = res.json()
                content = data["content"][0]["text"]
                return cls._parse_json_response(content, product, marketplace=marketplace)
        except httpx.HTTPStatusError as e:
            print("Claude status:", e.response.status_code)
            print("Claude response:", e.response.text[:1000])
            return cls._fallback_generator(product, product.brand or settings.DEFAULT_BRAND, marketplace=marketplace)
        except httpx.RequestError as e:
            print(f"Claude network error: {e}")
            return cls._fallback_generator(product, product.brand or settings.DEFAULT_BRAND, marketplace=marketplace)
        except Exception as e:
            print(f"Claude call failed ({e}); using template generator")
            return cls._fallback_generator(product, product.brand or settings.DEFAULT_BRAND, marketplace=marketplace)

    @classmethod
    def _enrich_with_apple_grade_specs_and_aplus(cls, product: Product, brand: str, draft: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adds the product's own attributes to the technical specs, filed under the Amazon
        product-type field they match. Nothing is defaulted: a spec or A+ block the model didn't
        write and the catalogue doesn't hold stays absent.
        """
        attrs = product.attributes or {}
        specs = dict(draft.get("technical_specs") or {})
        for k, v in attrs.items():
            if v and k not in specs:
                specs[str(k)] = str(v)

        ptd_defn = AmazonPTDService.get_ptd_definition(product.category or "General", product.name or "")
        for field in ptd_defn.get("required_fields", []) + ptd_defn.get("optional_fields", [])[:4]:
            if field in specs:
                continue
            field_lower = field.lower()
            for ak, av in attrs.items():
                if av and (ak.lower() in field_lower or field_lower in ak.lower()):
                    specs[field] = str(av)
                    break

        draft["technical_specs"] = specs
        draft["aplus_content"] = dict(draft.get("aplus_content") or {})
        return draft

    @classmethod
    def _rate_limit_cooldown(cls, res: httpx.Response) -> float:
        """Seconds to skip a model after a 429, from Retry-After when OpenRouter sends it."""
        retry_after = res.headers.get("retry-after")
        try:
            seconds = float(retry_after) if retry_after else DEFAULT_RATE_LIMIT_COOLDOWN_S
        except ValueError:
            seconds = DEFAULT_RATE_LIMIT_COOLDOWN_S
        return min(max(seconds, 1.0), MAX_RATE_LIMIT_COOLDOWN_S)

    @classmethod
    def _parse_json_response(cls, raw: Any, product: Product, marketplace: str = "amazon", fallback_on_error: bool = True) -> Optional[Dict[str, Any]]:
        """Parses model JSON. With fallback_on_error=False, returns None on bad output so the caller can try another model."""
        if not raw or not isinstance(raw, str) or not raw.strip():
            if not fallback_on_error:
                return None
            return cls._fallback_generator(product, product.brand or settings.DEFAULT_BRAND, marketplace=marketplace)

        clean = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
        clean = re.sub(r"```$", "", clean.strip(), flags=re.MULTILINE)
        json_match = re.search(r"(\{.*\})", clean, flags=re.DOTALL)
        if json_match:
            clean = json_match.group(1)

        try:
            parsed = cls._normalize_listing(json.loads(clean))
            if len(parsed["title"]) > 200:
                parsed["title"] = parsed["title"][:197] + "..."
            return cls._enrich_with_apple_grade_specs_and_aplus(product, product.brand or settings.DEFAULT_BRAND, parsed)
        except Exception:
            if not fallback_on_error:
                return None
            return cls._fallback_generator(product, product.brand or settings.DEFAULT_BRAND, marketplace=marketplace)

    @classmethod
    def _normalize_listing(cls, parsed: Any) -> Dict[str, Any]:
        """
        Gives model output the shape the draft code reads: missing keywords or specs become empty
        instead of failing with a KeyError, and a list sent as one string is split. Raises ValueError
        (so the next model is tried) when it isn't a usable listing: no title, description or bullets,
        or more than 10 bullets (models sometimes write the description into the bullet list).
        """
        if not isinstance(parsed, dict):
            raise ValueError("model output is not a JSON object")

        def as_list(value: Any, sep: str) -> List[str]:
            if isinstance(value, str):
                value = re.split(sep, value)
            if not isinstance(value, list):
                return []
            return [str(v).strip() for v in value if v is not None and str(v).strip()]

        parsed["title"] = str(parsed.get("title") or "").strip()
        parsed["bullets"] = as_list(parsed.get("bullets"), r"\n+")
        parsed["description"] = str(parsed.get("description") or "").strip()
        parsed["keywords"] = as_list(parsed.get("keywords"), r"[,\n]+")
        for key in ("technical_specs", "aplus_content"):
            if not isinstance(parsed.get(key), dict):
                parsed[key] = {}
        if not parsed["title"] or not parsed["description"] or not 1 <= len(parsed["bullets"]) <= 10:
            raise ValueError("model output is missing the title, description or bullets")
        return parsed

    @classmethod
    def _fallback_generator(cls, product: Product, brand: str, marketplace: str = "amazon") -> Dict[str, Any]:
        """Category-agnostic copy generator strictly grounded in verified product data."""
        p_name = product.name or "Product"
        category = product.category or "General"
        attrs = product.attributes or {}
        mp = (marketplace or "amazon").lower()
        
        # Extract specs dynamically (the Meesho category is a template id, not a product fact)
        spec_items = [f"{k}: {v}" for k, v in attrs.items() if v and str(k).strip().lower() != MEESHO_CATEGORY_ATTR.lower()]
        main_spec = attrs.get("Material") or attrs.get("Fabric") or attrs.get("Processor") or attrs.get("Type") or ""
        size_spec = attrs.get("Size") or attrs.get("Dimensions") or attrs.get("Capacity") or attrs.get("Weight") or ""
        care_spec = attrs.get("Care") or attrs.get("Warranty") or attrs.get("Usage") or ""
        color_spec = attrs.get("Colour") or attrs.get("Color") or ""
        included_spec = attrs.get("Included") or attrs.get("Sales Package") or attrs.get("Package Contents") or attrs.get("Count") or ""
        occasion_spec = attrs.get("Occasion") or attrs.get("Use") or ""
        pattern_spec = attrs.get("Pattern") or attrs.get("Print") or ""
        
        # Title construction
        title_components = [brand, p_name]
        if color_spec and str(color_spec).lower() not in p_name.lower():
            title_components.append(str(color_spec))
        if main_spec and str(main_spec).lower() not in p_name.lower():
            title_components.append(str(main_spec))
        # Meesho keeps size, weight and dimensions out of Product Name
        if size_spec and str(size_spec).lower() not in p_name.lower() and mp != "meesho":
            title_components.append(str(size_spec))

        # Attributes that don't fit are left out whole; only a name longer than the limit is cut, at a word
        max_title_len = title_limit(mp)
        title_components = [str(c) for c in title_components if c]
        while len(title_components) > 2 and len(" - ".join(title_components)) > max_title_len:
            title_components.pop()
        title = " - ".join(title_components)
        if len(title) > max_title_len:
            title = title[:max_title_len + 1].rsplit(" ", 1)[0].rstrip(" -,")

        # Bullets restate product attributes only; a bullet with no attribute behind it is left out
        bullets = [f"PRODUCT — {p_name} by {brand}."]
        if pattern_spec:
            bullets.append(f"STYLE & DESIGN — {pattern_spec}.")
        if main_spec:
            bullets.append(f"MATERIAL — {main_spec}.")
        elif spec_items:
            bullets.append(f"SPECIFICATIONS — {', '.join(spec_items[:3])}.")
        if size_spec:
            bullets.append(f"DIMENSIONS & SIZING — {size_spec}.")
        elif color_spec:
            bullets.append(f"FINISH — Available in {color_spec}." if mp == "meesho" else f"FINISH & COLOR — Available in {color_spec}.")
        if included_spec:
            bullets.append(f"PACKAGE CONTENTS — Includes {included_spec}.")
        elif occasion_spec:
            bullets.append(f"RECOMMENDED USE — For {occasion_spec}.")
        elif spec_items and len(spec_items) > 3:
            bullets.append(f"ADDITIONAL ATTRIBUTES — {', '.join(spec_items[3:6])}.")
        if care_spec:
            bullets.append(f"WASH & MAINTENANCE — {care_spec}." if mp == "meesho" else f"CARE & MAINTENANCE — {care_spec}.")
        elif attrs.get("Finish"):
            bullets.append(f"FINISH & TOUCH — Finished with {attrs.get('Finish')}.")

        # Description constructed strictly from actual specs
        desc_parts = [f"{p_name} by {brand}, in {category}."]
        if spec_items:
            desc_parts.append(f"Product details: {', '.join(spec_items)}.")
        if occasion_spec:
            desc_parts.append(f"For {occasion_spec}.")
        if care_spec:
            desc_parts.append(f"Maintenance guidance: {care_spec}.")
        desc = " ".join(desc_parts)

        keywords = [
            category.lower(),
            p_name.lower()[:30],
            f"{brand.lower()} {category.lower()}",
        ]

        draft_res = {
            "title": title,
            "bullets": bullets[:5],
            "description": desc,
            "keywords": keywords,
            "engine": TEMPLATE_ENGINE
        }
        return cls._enrich_with_apple_grade_specs_and_aplus(product, brand, draft_res)

