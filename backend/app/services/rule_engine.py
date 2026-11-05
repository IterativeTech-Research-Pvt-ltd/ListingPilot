import re
from typing import Dict, Any, List, Optional
from app.models.product import Product
from app.services.template_generator import CATEGORIES_INFO
from app.services.settings_service import SettingsService
from app.services.meesho_adapter import (
    MeeshoAdapter, PRODUCT_NAME_RULES, MEESHO_CATEGORY_ATTR,
)
from app.services.marketplace_limits import title_limit

HTML_TAG_PATTERN = re.compile(r"<[^>]+>", re.IGNORECASE)

# Claims a listing may make only when the product data states them in those words
CLAIM_TERMS = (
    "100%", "pure", "genuine", "authentic", "original", "handmade", "hand made", "handcrafted", "hand crafted",
    "organic", "eco friendly", "sustainable", "hypoallergenic", "anti bacterial", "antibacterial", "anti microbial",
    "waterproof", "water resistant", "rust proof", "rustproof", "fade proof", "fade resistant", "colourfast",
    "colorfast", "shrink proof", "non toxic", "bpa free", "food grade", "certified", "isi", "bis", "warranty",
    "guarantee", "guaranteed", "lifetime", "machine wash", "machine washable", "hand wash", "dry clean",
    "dishwasher safe", "microwave safe", "skin friendly", "dermatologically tested",
)
# Praise the data can't back; a warning, since it states no checkable fact
PUFFERY_TERMS = (
    "premium", "luxury", "luxurious", "durable", "long lasting", "high quality", "top quality", "best", "superior",
    "finest", "world class", "perfect", "ultimate", "flawless", "unmatched", "exquisite",
)


def _tokens(text: str) -> List[str]:
    """Lowercase words and numbers, plurals folded ('Sheets' -> 'sheet'), '100%' kept whole."""
    out = []
    for t in re.findall(r"\d+(?:\.\d+)?%?|[a-z]+", (text or "").lower()):
        out.append(t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") and not t[0].isdigit() else t)
    return out


def _has_phrase(tokens: List[str], phrase: List[str]) -> bool:
    n = len(phrase)
    return n > 0 and any(tokens[i:i + n] == phrase for i in range(len(tokens) - n + 1))


class RuleEngine:
    """
    Evaluates marketplace compliance rules across Amazon, Flipkart, and Meesho (RUL-1 through RUL-5).
    Rules adapt to each marketplace's specific schema and publishing constraints.
    """

    @classmethod
    def evaluate(cls, product: Product, draft: Dict[str, Any] = None, marketplace: str = "amazon") -> Dict[str, Any]:
        issues: List[Dict[str, Any]] = []
        score = 0
        mp = (marketplace or "amazon").lower()
        
        # 1. RUL-1: Required attributes per category
        cat_info = next((c for c in CATEGORIES_INFO if c["category"].lower() == product.category.lower()), None)
        if mp == "meesho":
            # The fields the product's own Meesho template marks compulsory, as the export checks them
            missing_attrs = cls._meesho_required_issues(product, issues)
        else:
            required_attrs = cat_info["required_attrs"] if cat_info else ["Material"]

            # Case-insensitive: the importer title-cases headers ("Thread count" is stored as "Thread Count")
            prod_attrs = {str(k).strip().lower(): v for k, v in (product.attributes or {}).items()}
            missing_attrs = [attr for attr in required_attrs if not str(prod_attrs.get(attr.lower(), "") or "").strip()]
            for miss in missing_attrs:
                issues.append({
                    "level": "error",
                    "kind": "attribute",
                    "field": miss,
                    "message": f"'{miss}' is required for category '{product.category}' and is missing in master catalogue data."
                })

        attr_score = max(0, 5 - len(missing_attrs) * 2)

        # 2. RUL-3: Photo count check (Marketplace-specific)
        img_count = product.image_count or (len(product.images) if product.images else 0)
        
        if mp == "amazon":
            min_images = cat_info["min_images"] if cat_info else 3
            if img_count < min_images:
                issues.append({
                    "level": "error",
                    "kind": "image",
                    "field": "images",
                    "message": f"Only {img_count} photo(s) attached. Amazon requires at least {min_images} photos (primary photo on plain white background)."
                })
                img_score = 1
            elif img_count < 5:
                issues.append({
                    "level": "warning",
                    "kind": "image",
                    "field": "images",
                    "message": f"{img_count} photos attached. 5 or more photos are recommended on Amazon for top conversion."
                })
                img_score = 3
            else:
                img_score = 5
        elif mp == "flipkart":
            min_images = 1
            if img_count < min_images:
                issues.append({
                    "level": "error",
                    "kind": "image",
                    "field": "images",
                    "message": "Flipkart requires at least 1 primary front-view image."
                })
                img_score = 1
            elif img_count < 3:
                issues.append({
                    "level": "warning",
                    "kind": "image",
                    "field": "images",
                    "message": f"{img_count} photo attached. Flipkart recommends 3+ angle photos."
                })
                img_score = 3
            else:
                img_score = 5
        else: # meesho
            min_images = 1
            if img_count < 1:
                issues.append({
                    "level": "error",
                    "kind": "image",
                    "field": "images",
                    "message": "Meesho requires at least 1 clear product photo."
                })
                img_score = 1
            else:
                img_score = 5

        # 3. Check Price
        if product.price <= 0:
            issues.append({
                "level": "error",
                "kind": "price",
                "field": "price",
                "message": "Selling price is missing or zero. Cannot publish without a valid price."
            })

        # Draft Content Checks (if draft exists)
        title_score = 0
        bullets_score = 0
        kw_score = 0
        
        if draft:
            title = draft.get("title", "")
            bullets = draft.get("bullets", [])
            desc = draft.get("description", "")
            keywords = draft.get("keywords", [])

            # RUL-2: Title length rules per marketplace
            t_len = len(title)
            if t_len == 0:
                issues.append({"level": "error", "kind": "title", "field": "title", "message": "Listing title is empty."})
            elif t_len > title_limit(mp):
                issues.append({
                    "level": "error",
                    "kind": "title",
                    "field": "title",
                    "message": f"Title is {t_len} characters long; {mp.capitalize()} caps titles at {title_limit(mp)} characters."
                })
                title_score = 2
            elif t_len < 40:
                issues.append({
                    "level": "warning",
                    "kind": "title",
                    "field": "title",
                    "message": f"Title is very short ({t_len} chars). Include brand name and primary specifications."
                })
                title_score = 3
            else:
                title_score = 5

            # RUL-4: Banned claims check across all listing text (dynamic via ADM-1)
            banned_claims = SettingsService.get_banned_claims()
            all_text_blocks = [title] + bullets + [desc]
            for text_block in all_text_blocks:
                if not text_block:
                    continue
                for claim in banned_claims:
                    if not claim:
                        continue
                    words = [re.escape(w) for w in claim.strip().split()]
                    pattern = re.compile(r"\b" + r"\s+".join(words) + r"\b", re.IGNORECASE)
                    match = pattern.search(text_block)
                    if match:
                        issues.append({
                            "level": "error",
                            "kind": "banned_claim",
                            "field": "content",
                            "message": f"Contains prohibited marketplace claim '{match.group(0)}'. Marketplaces reject promotional superlatives in product content."
                        })
                        break

            # Check Meesho Plain Text (No HTML)
            if mp == "meesho" and HTML_TAG_PATTERN.search(desc):
                issues.append({
                    "level": "error",
                    "kind": "html_tag",
                    "field": "description",
                    "message": "HTML tags detected in description. Meesho bulk upload sheets only accept plain text."
                })

            # Meesho's flagged words, Product Name rules and facts the data doesn't state
            if mp == "meesho":
                issues.extend(cls.meesho_copy_issues(product, draft))

            # Check Bullets
            if mp == "amazon" and len(bullets) < 5:
                issues.append({
                    "level": "warning",
                    "kind": "bullets",
                    "field": "bullets",
                    "message": f"Only {len(bullets)} bullet points provided; Amazon listings recommend 5 complete bullet points."
                })
                bullets_score = max(1, len(bullets))
            elif len(bullets) < 3:
                issues.append({
                    "level": "warning",
                    "kind": "bullets",
                    "field": "bullets",
                    "message": f"Only {len(bullets)} bullet points provided; at least 3 feature highlights recommended."
                })
                bullets_score = max(1, len(bullets))
            else:
                valid_bullets = [b for b in bullets if len(b) >= 20]
                bullets_score = 5 if len(valid_bullets) >= 4 else 4

            # Check Search Keywords
            kw_score = min(5, len(keywords))
        else:
            issues.append({
                "level": "info",
                "kind": "draft",
                "field": "draft",
                "message": f"AI listing content for {mp.capitalize()} not yet generated."
            })

        total_score = title_score + bullets_score + attr_score + kw_score + img_score
        has_errors = any(i["level"] == "error" for i in issues)

        return {
            "passed": not has_errors and draft is not None,
            "has_errors": has_errors,
            "score": total_score, # out of 25
            "quality_rating": "Excellent" if total_score >= 20 else "Good" if total_score >= 15 else "Needs Improvement",
            "marketplace": mp,
            "issues": issues,
            "checks_summary": {
                "attributes_ok": len(missing_attrs) == 0,
                "photos_ok": img_count >= (3 if mp == "amazon" else 1),
                "banned_claims_clean": not any(i["kind"] == "banned_claim" for i in issues),
                "title_length_ok": not any(i["kind"] == "title" and i["level"] == "error" for i in issues)
            }
        }

    @classmethod
    def _meesho_required_issues(cls, product: Product, issues: List[Dict[str, Any]]) -> List[str]:
        """
        Adds an error for each compulsory field of the product's Meesho template its data lacks (or holds
        a value the template doesn't list), or one error when no Meesho category is chosen yet.
        Seller details are left to Settings and images to their own check. Returns the fields missing.
        """
        missing = MeeshoAdapter.missing_fields({"product": product, "draft": None})
        if not missing["template"]:
            # No category chosen, a stale choice, or an unreadable template: the adapter's own reason
            reason = missing["other"][0]["reason"]
            issues.append({
                "level": "error",
                "kind": "meesho_category",
                "field": MEESHO_CATEGORY_ATTR,
                "message": f"Meesho category: {reason}. Its template decides the fields Meesho requires.",
            })
            return [MEESHO_CATEGORY_ATTR]
        breadcrumb = missing["meesho_category"]["breadcrumb"]
        for f in missing["fields"]:
            issues.append({
                "level": "error",
                "kind": "attribute",
                "field": f["field"],
                "message": f"Meesho's {breadcrumb} template requires '{f['field']}': {f['reason']}.",
            })
        return [f["field"] for f in missing["fields"]]

    @classmethod
    def meesho_copy_issues(cls, product: Product, draft: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Deterministic checks on Meesho copy, before it can be approved. Errors: a word Meesho's QC flags,
        a weight, dimension, price or other marketplace's name in the title, and any fact the product
        data doesn't state (copy_fact_issues, with the Meesho template's option words as the category's
        fact vocabulary). Praise words are a warning.
        """
        title = draft.get("title") or ""
        bullets = list(draft.get("bullets") or [])
        text = " ".join([title, draft.get("description") or ""] + bullets)
        issues: List[Dict[str, Any]] = []

        flagged = [w for w in MeeshoAdapter.flagged_words() if re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE)]
        if flagged:
            issues.append({
                "level": "error",
                "kind": "meesho_flagged_word",
                "field": "description",
                "message": f"Meesho's QC flags {', '.join(repr(w) for w in flagged)}; reword the listing without them.",
            })
        for what, pattern in PRODUCT_NAME_RULES:
            m = re.search(pattern, title, flags=re.IGNORECASE)
            if m:
                issues.append({
                    "level": "error",
                    "kind": "title",
                    "field": "title",
                    "message": f"The title contains {what} ('{m.group(0).strip()}'), which Meesho doesn't allow in Product Name.",
                })
                break

        # Listing text is about the product, in English letters: no notes to the reader about searching
        meta = re.search(r"\b(?:shoppers?|search(?:e[sd]|ing)?|keywords?)\b", text, flags=re.IGNORECASE)
        if meta:
            issues.append({
                "level": "error",
                "kind": "copy_style",
                "field": "description",
                "message": f"The copy talks about '{meta.group(0)}'; write only about the product.",
            })
        if re.search(r"[^\x00-\u024F\u2010-\u20BF\u2122]", text):
            issues.append({
                "level": "error",
                "kind": "copy_style",
                "field": "description",
                "message": "The copy uses non-English script; write Hinglish words in English letters.",
            })

        tmpl, _ = MeeshoAdapter.resolve_item_template({"product": product})
        issues.extend(cls.copy_fact_issues(
            product, draft, vocabulary=MeeshoAdapter.fact_vocabulary(tmpl), extra_source=tmpl["breadcrumb"] if tmpl else "",
        ))
        return issues

    @classmethod
    def copy_fact_issues(cls, product: Product, draft: Dict[str, Any], vocabulary: List[str] = (),
                         extra_source: str = "") -> List[Dict[str, Any]]:
        """
        Facts the listing states that the product data (name, category, brand, notes, attributes) doesn't:
        numbers, which also catches converted or rounded measurements; claims (CLAIM_TERMS); and the
        category's own fact words (`vocabulary`, e.g. a template's fabrics and colours). Each is an
        error, since AI copy never invents product facts; praise words (PUFFERY_TERMS) are a warning.
        """
        attrs = {k: v for k, v in (product.attributes or {}).items() if str(k).strip().lower() != MEESHO_CATEGORY_ATTR.lower()}
        source = _tokens(" ".join([
            product.name or "", product.category or "", product.brand or "", product.description or "", extra_source,
            *(f"{k} {v}" for k, v in attrs.items() if v is not None),
        ]))
        copy = _tokens(" ".join([draft.get("title") or "", draft.get("description") or "", *(draft.get("bullets") or [])]))
        copy_set, source_set = set(copy), set(source)

        def number(t: str) -> Optional[float]:
            return float(t.rstrip("%")) if t[0].isdigit() else None

        source_numbers = {number(t) for t in source if number(t) is not None}
        numbers = sorted({t.rstrip("%") for t in copy if number(t) is not None and number(t) not in source_numbers},
                         key=lambda t: float(t))
        claims = [c for c in CLAIM_TERMS if _has_phrase(copy, _tokens(c)) and not _has_phrase(source, _tokens(c))]
        # An option is stated when the data has all its words: 'fitted double' + 'Bedsheets' states 'Fitted Bedsheets'
        facts = []
        for word in vocabulary:
            phrase = _tokens(word)
            if phrase and phrase[0] in copy_set and _has_phrase(copy, phrase) and not set(phrase) <= source_set:
                facts.append(word)
        # 'Navy Blue' unstated already covers its 'Blue'
        facts = [f for f in facts if not any(o != f and _has_phrase(_tokens(o), _tokens(f)) for o in facts)]
        puffery = [p for p in PUFFERY_TERMS if _has_phrase(copy, _tokens(p)) and not _has_phrase(source, _tokens(p))]

        issues: List[Dict[str, Any]] = []
        if numbers:
            issues.append({
                "level": "error", "kind": "unsupported_fact", "field": "content",
                "message": f"States the number(s) {', '.join(numbers)}, which the product data doesn't; "
                           f"write measurements exactly as the data gives them (no conversions) or leave them out.",
            })
        stated = claims + facts
        if stated:
            issues.append({
                "level": "error", "kind": "unsupported_fact", "field": "content",
                "message": f"States {', '.join(repr(s) for s in stated)}, which the product data doesn't; "
                           f"take them out, or add them to the product's attributes if they're true.",
            })
        if puffery:
            issues.append({
                "level": "warning", "kind": "puffery", "field": "content",
                "message": f"Praise the data can't back: {', '.join(repr(p) for p in puffery)}. State facts instead.",
            })
        return issues
