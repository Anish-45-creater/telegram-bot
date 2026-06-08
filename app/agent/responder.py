"""
app/agent/responder.py — Format results into business discovery layout.
"""
NUMBER_EMOJIS = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟",
                 "1️⃣1️⃣","1️⃣2️⃣","1️⃣3️⃣","1️⃣4️⃣","1️⃣5️⃣","1️⃣6️⃣","1️⃣7️⃣","1️⃣8️⃣","1️⃣9️⃣","2️⃣0️⃣"]
DIVIDER = "\n════════════════════"

def _v(val, fallback="Not Available"):
    if not val or str(val).strip() in ("","null","None","0"): return fallback
    return str(val).strip()

def _format_list(user_query, data, header_prefix=""):
    results  = data.get("results", [])
    location = _v(data.get("location"), "Not Detected")
    category = _v(data.get("category"), "Business")
    if not results:
        return (f"⚠️ No results found for:\n{user_query}\n\n"
                "Tips:\n• Include city name — e.g. Top 10 electricians in Chennai\n"
                "• Try 'near me' and share your location")
    lines = [f"🔍 {header_prefix}SEARCH: {user_query}",
             f"📍 LOCATION: {location}", f"🏷 CATEGORY: {category}",
             f"📊 RESULTS: {len(results)}"]
    for i, biz in enumerate(results):
        emoji   = NUMBER_EMOJIS[i] if i < len(NUMBER_EMOJIS) else f"{i+1}."
        rating  = _v(biz.get("rating"),"")
        reviews = _v(biz.get("reviews"),"")
        rating_line = f"{rating}/5 ({reviews} reviews)" if rating and reviews else \
                      (f"{rating}/5" if rating else "Not Available")
        lines += [DIVIDER, f"\n{emoji} {_v(biz.get('name'),'Unknown')}",
                  f"📞 Phone: {_v(biz.get('phone'))}",
                  f"📍 Address: {_v(biz.get('address'))}",
                  f"⭐ Rating: {rating_line}",
                  f"🌐 Website: {_v(biz.get('website'))}"]
        if biz.get("distance"): lines.append(f"📏 Distance: {biz['distance']}")
        if biz.get("type"):     lines.append(f"📝 {biz['type']}")
    lines += [DIVIDER, f"\n✅ Category: {category}", f"✅ Location: {location}",
              f"✅ Total: {len(results)}", "✅ Sorted By: Rating · Reviews · Reputation",
              "\n💡 Reply 'show more' to get more results!"]
    return "\n".join(lines)

def format_business_results(user_query, data):
    return _format_list(user_query, data)

def format_nearby_results(user_query, data):
    return _format_list(user_query, data, header_prefix="📍 NEARBY ")

def format_error(user_query, error):
    return (f"⚠️ Sorry, couldn't find results for:\n{user_query}\n\n"
            "Try:\n• Top 10 plumbers in Chennai\n• Best hospitals in Bangalore\n"
            "• Hotels near me (share location)")
