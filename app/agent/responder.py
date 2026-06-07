"""
app/agent/responder.py — Format SerpAPI results into the business discovery layout.
"""

NUMBER_EMOJIS = [
    "1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟",
    "1️⃣1️⃣","1️⃣2️⃣","1️⃣3️⃣","1️⃣4️⃣","1️⃣5️⃣",
    "1️⃣6️⃣","1️⃣7️⃣","1️⃣8️⃣","1️⃣9️⃣","2️⃣0️⃣",
]
DIVIDER = "\n════════════════════"


def _v(val, fallback="Not Available"):
    if not val or str(val).strip() in ("", "null", "None", "0"):
        return fallback
    return str(val).strip()


def format_business_results(user_query: str, data: dict) -> str:
    results  = data.get("results", [])
    location = _v(data.get("location"), "Not Detected")
    category = _v(data.get("category"), "Business")

    if not results:
        return (
            f"⚠️ No results found for:\n{user_query}\n\n"
            "Tips:\n"
            "• Include the city name — e.g. Top 10 electricians in Chennai\n"
            "• Try a different category name\n"
            "• Make sure your SERPAPI_KEY is set correctly in Render env vars"
        )

    lines = [
        f"🔍 SEARCH QUERY: {user_query}",
        f"📍 LOCATION: {location}",
        f"🏷 CATEGORY: {category}",
        f"📊 RESULTS FOUND: {len(results)}",
    ]

    for i, biz in enumerate(results):
        emoji   = NUMBER_EMOJIS[i] if i < len(NUMBER_EMOJIS) else f"{i+1}."
        phone   = _v(biz.get("phone"))
        address = _v(biz.get("address"))
        website = _v(biz.get("website"))
        biz_type = _v(biz.get("type"), "")

        rating  = _v(biz.get("rating"), "")
        reviews = _v(biz.get("reviews"), "")
        if rating and reviews:
            rating_line = f"{rating}/5  ({reviews} reviews)"
        elif rating:
            rating_line = f"{rating}/5"
        else:
            rating_line = "Not Available"

        lines.append(DIVIDER)
        lines.append(f"\n{emoji} {_v(biz.get('name'), 'Unknown')}")
        lines.append(f"📞 Phone: {phone}")
        lines.append(f"📍 Address: {address}")
        lines.append(f"⭐ Rating: {rating_line}")
        lines.append(f"🌐 Website: {website}")
        if biz_type:
            lines.append(f"📝 {biz_type}")

    lines.append(DIVIDER)
    lines.append(f"\n✅ Category: {category}")
    lines.append(f"✅ Location: {location}")
    lines.append(f"✅ Total Results: {len(results)}")
    lines.append("✅ Sorted By: Rating · Reviews · Reputation")
    lines.append("\n💡 Reply with a new query to search again!")

    return "\n".join(lines)


def format_error(user_query: str, error: str) -> str:
    return (
        f"⚠️ Sorry, search failed for:\n{user_query}\n\n"
        "Please try again in a moment.\n\n"
        "Example queries:\n"
        "• Top 10 plumbers in Chennai\n"
        "• Best electricians in Bangalore\n"
        "• Top hospitals in Coimbatore"
    )
