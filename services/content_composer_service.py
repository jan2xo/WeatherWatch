import logging
import string

from services.content_composer_config_service import get_composer_config
from services.forecast_parser import (
    build_affected_weather_caption_detail,
    build_structured_forecast_caption_detail,
    format_hashtag,
)


LOGGER = logging.getLogger(__name__)


def join_areas(areas):
    cleaned = [str(area).strip() for area in (areas or []) if str(area).strip()]

    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} at {cleaned[1]}"

    return f"{', '.join(cleaned[:-1])}, at {cleaned[-1]}"


def split_story_lines(text):
    return [line.strip() for line in (text or "").split("\n\n") if line.strip()]


def normalize_match_value(value):
    return " ".join(str(value or "").strip().casefold().split())


def find_monsoon_system(parsed_forecast_text, forecast_data, config):
    systems = config["composer"]["monsoon"]["systems"]
    detected_system = normalize_match_value(
        forecast_data.get("affected_weather_system")
    )
    raw_text = normalize_match_value(parsed_forecast_text)

    for system_name, settings in systems.items():
        aliases = {
            normalize_match_value(system_name),
            *(
                normalize_match_value(alias)
                for alias in settings.get("aliases", [])
            ),
        }

        if detected_system and detected_system in aliases:
            return settings

        if any(alias and alias in raw_text for alias in aliases):
            return settings

    return None


def safe_render(template, values, fallback, label):
    try:
        fields = {
            field_name
            for _, field_name, _, _ in string.Formatter().parse(template)
            if field_name
        }
        missing = [
            field
            for field in fields
            if values.get(field) is None or values.get(field) == ""
        ]

        if missing:
            raise ValueError(
                f"missing values: {', '.join(sorted(missing))}"
            )

        rendered = template.format_map(values).strip()
        if not rendered:
            raise ValueError("rendered text is empty")

        return rendered
    except (KeyError, ValueError) as error:
        LOGGER.warning(
            "Composer template %s could not be rendered; using fallback: %s",
            label,
            error,
        )
        return fallback


def compose_monsoon_update(
    parsed_forecast_text,
    forecast_data,
    config,
    system_config,
):
    composer = config["composer"]
    fallback = composer["fallback"]
    areas_text = join_areas(forecast_data.get("affected_areas"))
    display_name = system_config["display_name"]
    values = {
        "display_name": display_name,
        "areas_text": areas_text,
        "subject": display_name,
        "parsed_forecast_text": " ".join(
            (parsed_forecast_text or "").split()
        ),
    }
    headline = safe_render(
        system_config["headline_template"],
        values,
        fallback["headline"],
        "monsoon.headline_template",
    )
    summary = safe_render(
        system_config["summary_template"],
        values,
        fallback["summary"],
        "monsoon.summary_template",
    )

    return {
        "content_type": "monsoon_update",
        "primary_subject": display_name,
        "headline": headline,
        "summary": summary,
        "body_lines": [],
        "source_line": composer["default_source_line"],
    }


def compose_cyclone_update(forecast_data, config):
    composer = config["composer"]
    cyclone_config = composer["cyclone"]
    classification = forecast_data.get("cyclone_classification")
    local_name = forecast_data.get("cyclone_name_local")
    hashtag = format_hashtag(local_name)
    subject = " ".join(
        part for part in (classification, hashtag) if part
    )
    story_lines = split_story_lines(
        build_structured_forecast_caption_detail(forecast_data)
    )
    affected_line = build_affected_weather_caption_detail(forecast_data)

    if affected_line:
        story_lines.append(affected_line)

    if story_lines:
        summary = story_lines[0]
        body_lines = story_lines[1:]
    else:
        summary = cyclone_config["fallback_summary"]
        body_lines = []

    headline = safe_render(
        cyclone_config["headline_template"],
        {
            "display_name": "",
            "areas_text": "",
            "subject": subject,
            "parsed_forecast_text": "",
        },
        cyclone_config["fallback_headline"],
        "cyclone.headline_template",
    )

    return {
        "content_type": "cyclone_update",
        "primary_subject": subject or cyclone_config["fallback_headline"],
        "headline": headline,
        "summary": summary,
        "body_lines": body_lines,
        "source_line": composer["default_source_line"],
    }


def compose_fallback_update(parsed_forecast_text, config):
    composer = config["composer"]
    fallback = composer["fallback"]
    cleaned_text = " ".join((parsed_forecast_text or "").split())
    values = {
        "display_name": "",
        "areas_text": "",
        "subject": fallback["primary_subject"],
        "parsed_forecast_text": cleaned_text,
    }

    return {
        "content_type": "general_weather",
        "primary_subject": safe_render(
            fallback["primary_subject"],
            values,
            "Weather Update",
            "fallback.primary_subject",
        ),
        "headline": safe_render(
            fallback["headline"],
            values,
            "Weather Update",
            "fallback.headline",
        ),
        "summary": safe_render(
            fallback["summary"],
            values,
            "Weather update information is temporarily unavailable.",
            "fallback.summary",
        ),
        "body_lines": [],
        "source_line": composer["default_source_line"],
    }


def compose_weather_content(
    parsed_forecast_text,
    forecast_data,
    provider_metadata=None,
    composer_config=None,
):
    data = forecast_data if isinstance(forecast_data, dict) else {}
    config = composer_config or get_composer_config()

    try:
        monsoon_system = find_monsoon_system(
            parsed_forecast_text,
            data,
            config,
        )

        if data.get("cyclone_classification") and data.get(
            "cyclone_name_local"
        ):
            content = compose_cyclone_update(data, config)
        elif monsoon_system:
            content = compose_monsoon_update(
                parsed_forecast_text,
                data,
                config,
                monsoon_system,
            )
        else:
            content = compose_fallback_update(
                parsed_forecast_text,
                config,
            )
    except Exception as error:
        LOGGER.warning(
            "Content composer failed; using default configuration: %s",
            error,
        )
        content = compose_fallback_update(
            parsed_forecast_text,
            get_composer_config(),
        )

    if provider_metadata:
        content["provider_metadata"] = dict(provider_metadata)

    return content
