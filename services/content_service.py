MODIFY_HELP_TEXT = (
    "<b>Modify Help:</b>\n"
    "/modify + full caption updates the Facebook/Instagram caption and derives the GPX headline from the first line.\n"
    "/modify HEADLINE: updates only the GPX graphic headline.\n"
    "/modify HEADLINE: + CAPTION: lets you override the GPX headline while using a separate Facebook caption.\n"
    "Attach a photo with /modify to replace the image.\n"
    "HEADLINE: affects only the graphic. It does not change the Facebook caption unless CAPTION: is also supplied."
)


def format_storm_label(storm):
    return f"{storm['category']} {storm['hashtag']}"


def build_caption_opener(headline, emoji):
    return f"{emoji} {' '.join(headline.splitlines())}!"


def format_storm_detail(storm):
    label = format_storm_label(storm)

    if storm.get("distance_km") and storm.get("location"):
        return f"{label} na nasa {storm['distance_km']} km {storm['location']}"

    return label


def join_filipino(items):
    if len(items) == 0:
        return ""

    if len(items) == 1:
        return items[0]

    if len(items) == 2:
        return f"{items[0]} at {items[1]}"

    return f"{', '.join(items[:-1])}, at {items[-1]}"


def format_provider_display(job):
    return (
        job.get("provider_display")
        or job.get("provider_url")
        or job.get("provider")
        or "Provider"
    ).upper()


def build_source_block(job):
    """
    Forecast text comes from PAGASA.
    Map/visualization comes from the active provider: Windy, PANaHON, etc.
    """

    provider_display = job.get("provider_display") or job.get("provider") or "Provider"
    provider_url = job.get("provider_url") or job.get("url") or ""

    if provider_url:
        return f"Forecast: PAGASA | pagasa.dost.gov.ph\nMap: {provider_display.upper()} | {provider_url}"

    return f"Forecast: PAGASA\nMap: {provider_display.upper()}"


def build_graphic_headline(job):
    forecast = job.get("forecast", {})
    storms = forecast.get("storms", [])

    if forecast.get("has_storms"):
        if len(storms) >= 2:
            return "DALAWANG BAGYO,\nPATULOY NA BINABANTAYAN"

        storm = storms[0]
        return (
            f"{storm['category'].upper()}\n"
            f"{storm['hashtag']}\n"
            "PATULOY NA BINABANTAYAN"
        )

    if forecast.get("habagat"):
        return "HABAGAT\nNAKAAAPEKTO SA LUZON"

    return job.get(
        "headline",
        "MAINIT AT MAALINSANGANG PANAHON,\nMAY PAMINSAN-MINSANG PAG-ULAN",
    )


def build_facebook_caption(job):
    headline = job.get("headline", "WEATHER UPDATE")
    forecast = job.get("forecast", {})
    storms = forecast.get("storms", [])
    bulletin_lines = forecast.get("bulletin_lines", [])
    source_block = build_source_block(job)

    if forecast.get("has_storms"):
        storm_details = join_filipino([
            format_storm_detail(storm)
            for storm in storms
        ])

        opener = build_caption_opener(headline, "🌀")

        bulletin = ""
        if bulletin_lines:
            bulletin = "\n\n" + "\n".join(bulletin_lines)

        return (
            f"{opener}\n\n"
            f"Batay sa pinakahuling weather bulletin ng PAGASA, patuloy na mino-monitor ang {storm_details}."
            f"{bulletin}\n\n"
            f"{source_block}\n\n"
            "#WeatherWatch #NorthLuzonWeatherWatch"
        )

    if bulletin_lines:
        return (
            f"📡 {headline}\n\n"
            "Batay sa pinakahuling weather bulletin ng PAGASA:\n\n"
            f"{chr(10).join(bulletin_lines)}\n\n"
            f"{source_block}\n\n"
            "#WeatherWatch #NorthLuzonWeatherWatch"
        )

    return (
        f"📡 {headline}\n\n"
        "Batay sa pinakahuling weather bulletin ng PAGASA, patuloy nating mino-monitor ang lagay ng panahon sa North Luzon.\n\n"
        f"{source_block}\n\n"
        "#WeatherWatch #NorthLuzonWeatherWatch"
    )


def build_captions(job):
    facebook_caption = build_facebook_caption(job)
    provider_display = format_provider_display(job)

    telegram_caption = (
        "🤖 <b>WEATHERWATCH GENERATED UPDATE</b>\n\n"
        "Status: <b>Pending Approval</b>\n"
        f"Provider: <b>{provider_display}</b>\n\n"
        f"<b>Facebook Caption Preview:</b>\n{facebook_caption}"
    )

    return {
        "telegram": telegram_caption,
        "facebook": facebook_caption,
        "instagram": facebook_caption,
    }


def build_telegram_review_caption(job, current_job):
    return (
        f"{job['captions']['telegram']}\n\n"
        f"🆔 Job ID: <code>{current_job['job_id']}</code>\n"
        f"Status: <b>{current_job['status']}</b>\n\n"
        "<b>Commands:</b>\n"
        "/manual\n"
        "/approve\n"
        "/reject\n"
        "/retry_publish\n"
        "/fbstatus\n"
        "/fb_reconnect\n"
        "/fb_set_token\n\n"
        f"{MODIFY_HELP_TEXT}\n\n"
        "<b>Example:</b>\n"
        "/modify\n"
        "🌀 YOUR OPENER HERE!\n\n"
        "UPDATE: ..."
    )
