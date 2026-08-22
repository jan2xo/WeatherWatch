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
    Map/visualization comes from the sole operational provider: WINDY.
    """

    provider_display = job.get("provider_display") or job.get("provider") or "Provider"
    provider_url = job.get("provider_url") or job.get("url") or ""
    forecast_source = (
        job.get("forecast", {})
        .get("composed_content", {})
        .get("source_line")
        or "Forecast: PAGASA | pagasa.dost.gov.ph"
    )

    if provider_url:
        return f"{forecast_source}\nMap: {provider_display.upper()} | {provider_url}"

    return f"{forecast_source}\nMap: {provider_display.upper()}"


def build_graphic_headline(job):
    forecast = job.get("forecast", {})
    storms = forecast.get("storms", [])
    composed_content = forecast.get("composed_content") or {}

    if forecast.get("has_storms"):
        if len(storms) >= 2:
            return "DALAWANG BAGYO,\nPATULOY NA BINABANTAYAN"

        storm = storms[0]
        return (
            f"{storm['category'].upper()}\n"
            f"{storm['hashtag']}\n"
            "PATULOY NA BINABANTAYAN"
        )

    composed_headline = composed_content.get("headline")
    if composed_headline and composed_content.get("content_type") != (
        "general_weather"
    ):
        graphic_headline = composed_headline.upper()
        for action in (" NAKAAAPEKTO ", " BINABANTAYAN "):
            if action in graphic_headline:
                return graphic_headline.replace(
                    action,
                    f"\n{action.strip()} ",
                    1,
                )
        return graphic_headline

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
    composed_content = forecast.get("composed_content") or {}

    if forecast.get("has_storms"):
        storm_details = join_filipino([
            format_storm_detail(storm)
            for storm in storms
        ])
        structured_detail = forecast.get("structured_caption_detail")
        affected_weather_detail = forecast.get("affected_weather_caption_detail")

        opener = build_caption_opener(headline, "🌀")

        use_composed_story = (
            len(storms) == 1
            and composed_content.get("content_type") == "cyclone_update"
            and composed_content.get("summary")
        )
        details = (
            composed_content["summary"]
            if use_composed_story
            else structured_detail
            or f"Batay sa pinakahuling weather bulletin ng PAGASA, patuloy na mino-monitor ang {storm_details}."
        )

        bulletin_lines = [
            line
            for line in bulletin_lines
            if line != affected_weather_detail
        ]

        bulletin_parts = (
            list(composed_content.get("body_lines", []))
            if use_composed_story
            else []
        )

        if affected_weather_detail and not use_composed_story:
            bulletin_parts.append(affected_weather_detail)

        if bulletin_lines:
            bulletin_parts.extend(bulletin_lines)

        bulletin = ""
        if bulletin_parts:
            bulletin = "\n\n" + "\n".join(bulletin_parts)

        return (
            f"{opener}\n\n"
            f"{details}"
            f"{bulletin}\n\n"
            f"{source_block}\n\n"
            "#WeatherWatch #NorthLuzonWeatherWatch"
        )

    if composed_content.get("summary"):
        opener = build_caption_opener(headline, "📡")
        story_parts = [
            composed_content["summary"],
            *composed_content.get("body_lines", []),
        ]
        story = "\n\n".join(
            part for part in story_parts if part
        )

        return (
            f"{opener}\n\n"
            f"{story}\n\n"
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
    post_type = current_job.get("post_type", "image").upper()
    text_notice = (
        "\n<b>Facebook will publish this as a text-only post.</b>\n"
        if post_type == "TEXT"
        else ""
    )
    windy_line = (
        f"Windy Layer: <b>{current_job.get('windy_layer_label')}</b>\n"
        if current_job.get("windy_layer_label")
        else ""
    )
    return (
        f"{job['captions']['telegram']}\n\n"
        f"🆔 Job ID: <code>{current_job['job_id']}</code>\n"
        f"Status: <b>{current_job['status']}</b>\n"
        f"Post Type: <b>{post_type}</b>\n"
        f"{windy_line}"
        f"{text_notice}\n"
        "<b>Commands:</b>\n"
        "/manual\n"
        "/post_type\n"
        "/approve\n"
        "/text_approve\n"
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
