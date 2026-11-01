import re
from typing import Dict, Any, List
from app.models.product import Product
from app.services.template_generator import CATEGORIES_INFO
from app.services.settings_service import SettingsService
from app.services.meesho_adapter import MEESHO_FLAGGED_WORDS

HTML_TAG_PATTERN = re.compile(r"<[^>]+>", re.IGNORECASE)


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
            elif mp == "amazon" and t_len > 200:
                issues.append({
                    "level": "error",
                    "kind": "title",
                    "field": "title",
                    "message": f"Title is {t_len} characters long; Amazon strictly caps titles at 200 characters."
                })
                title_score = 2
            elif mp == "flipkart" and t_len > 120:
                issues.append({
                    "level": "error",
                    "kind": "title",
                    "field": "title",
                    "message": f"Title is {t_len} characters long; Flipkart recommends titles under 120 characters."
                })
                title_score = 2
            elif mp == "meesho" and t_len > 100:
                issues.append({
                    "level": "error",
                    "kind": "title",
                    "field": "title",
                    "message": f"Title is {t_len} characters long; Meesho supplier catalog strictly caps titles at 100 characters."
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

            # Words Meesho's catalogue QC flags as warnings in the product description
            if mp == "meesho":
                meesho_text = " ".join([title, desc] + list(bullets))
                flagged = [w for w in MEESHO_FLAGGED_WORDS if re.search(rf"\b{w}\b", meesho_text, re.IGNORECASE)]
                if flagged:
                    issues.append({
                        "level": "warning",
                        "kind": "meesho_flagged_word",
                        "field": "description",
                        "message": f"Meesho QC flags {', '.join(repr(w) for w in flagged)} in listing text. Reword to avoid the warning."
                    })

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
