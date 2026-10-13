
import re
from datetime import datetime, time, timezone
from urllib.parse import quote, urlsplit

import httpx
import streamlit as st


st.set_page_config(
    page_title="URL Shortener",
    page_icon="🔗",
    layout="wide",
)

st.title("🔗 URL Shortener")
st.caption(
    "Create short links, set expiration dates, "
    "and monitor click analytics."
)

# The URL Shortener runs through the existing FastAPI backend.
if "url_api_base" not in st.session_state:
    st.session_state.url_api_base = "http://127.0.0.1:8000"

with st.sidebar:
    st.header("API Connection")
    api_base = st.text_input(
        "FastAPI base URL",
        key="url_api_base",
    ).rstrip("/")

    if st.button("Check connection"):
        try:
            response = httpx.get(
                f"{api_base}/health",
                timeout=10,
                follow_redirects=False,
            )
            response.raise_for_status()
            result = response.json()
            if result.get("status") == "ok":
                st.success("API and database connected")
            else:
                st.warning(f"API response: {result}")
        except httpx.HTTPError as exc:
            st.error(f"Connection failed: {exc}")
        except ValueError:
            st.error("Invalid API response")


def api_error(response):
    """Extract a safe, readable API error."""
    try:
        body = response.json()
        error = body.get("error", {})
        if isinstance(error, dict):
            return (
                f"{error.get('code', 'error')}: "
                f"{error.get('message', 'Request failed')}"
            )
    except ValueError:
        pass

    return f"Request failed with HTTP {response.status_code}"


def valid_api_base(value):
    parsed = urlsplit(value)
    return (
        parsed.scheme in ("http", "https")
        and bool(parsed.netloc)
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )


def valid_http_url(value):
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.netloc)
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


def create_short_url(base, payload):
    response = httpx.post(
        f"{base}/api/urls",
        json=payload,
        timeout=20,
        follow_redirects=False,
    )
    if response.status_code != 201:
        raise ValueError(api_error(response))
    return response.json()


def get_analytics(base, short_code):
    safe_code = quote(short_code, safe="")
    response = httpx.get(
        f"{base}/api/urls/{safe_code}/analytics",
        timeout=15,
        follow_redirects=False,
    )
    if response.status_code != 200:
        raise ValueError(api_error(response))
    return response.json()


tab1, tab2 = st.tabs([
    "Create Short URL",
    "Click Analytics",
])

with tab1:
    st.subheader("Create a short link")

    with st.form("create_url_form"):
        original_url = st.text_input(
            "Original URL",
            placeholder="https://www.example.com/very/long/link",
        )

        custom_code = st.text_input(
            "Custom alias (optional)",
            placeholder="my-project",
            help=(
                "3 to 32 characters. "
                "Letters, numbers, hyphens and underscores."
            ),
        )

        use_expiration = st.checkbox(
            "Set expiration date",
            value=False,
        )

        expiration_date = None
        if use_expiration:
            expiration_date = st.date_input(
                "Expiration date",
                value=datetime.now(timezone.utc).date(),
            )

        submitted = st.form_submit_button(
            "Create Short URL",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        original_url = original_url.strip()
        custom_code = custom_code.strip()

        if not valid_api_base(api_base):
            st.error("Enter a valid FastAPI base URL.")

        elif not valid_http_url(original_url):
            st.error("Enter a valid HTTP or HTTPS destination URL.")

        elif custom_code and not re.fullmatch(
            r"[A-Za-z0-9_-]{3,32}",
            custom_code,
        ):
            st.error(
                "Alias must contain 3–32 letters, numbers, "
                "hyphens, or underscores."
            )

        else:
            payload = {"url": original_url}

            if custom_code:
                payload["customCode"] = custom_code

            if use_expiration and expiration_date:
                expires_at = datetime.combine(
                    expiration_date,
                    time(23, 59, 59),
                    tzinfo=timezone.utc,
                )
                payload["expiresAt"] = expires_at.isoformat()

            try:
                with st.spinner("Creating short URL..."):
                    result = create_short_url(api_base, payload)

                st.session_state["latest_short_url"] = result
                st.success("Short URL created successfully!")

            except httpx.HTTPError as exc:
                st.error(f"API connection error: {exc}")

            except ValueError as exc:
                st.error(str(exc))

    result = st.session_state.get("latest_short_url")

    if result:
        st.divider()
        st.subheader("Your shortened URL")

        short_url = result.get("shortUrl", "")
        short_code = result.get("shortCode", "")

        st.code(short_url, language=None)

        if short_url and short_url.startswith(
            ("http://", "https://")
        ):
            st.link_button(
                "Open Short URL",
                short_url,
                use_container_width=True,
            )

        col1, col2 = st.columns(2)

        with col1:
            st.metric("Short Code", short_code)

        with col2:
            st.metric(
                "Expiration",
                str(result.get("expiresAt") or "No expiration"),
            )

        st.caption("Original destination")
        st.write(result.get("originalUrl", ""))

        st.info(
            "Use the short link to visit the destination. "
            "You can inspect its click count in the Analytics tab."
        )


with tab2:
    st.subheader("URL Analytics")

    st.write(
        "Enter a short code to see the click count "
        "and the latest access timestamp."
    )

    default_code = ""
    latest = st.session_state.get("latest_short_url")
    if latest:
        default_code = latest.get("shortCode", "")

    with st.form("analytics_form"):
        analytics_code = st.text_input(
            "Short Code",
            value=default_code,
            placeholder="abc123",
        )

        analytics_submit = st.form_submit_button(
            "Get Analytics",
            type="primary",
            use_container_width=True,
        )

    if analytics_submit:
        analytics_code = analytics_code.strip()

        if not re.fullmatch(
            r"[A-Za-z0-9_-]{1,64}",
            analytics_code,
        ):
            st.error("Enter a valid short code.")

        elif not valid_api_base(api_base):
            st.error("Enter a valid FastAPI base URL.")

        else:
            try:
                with st.spinner("Loading analytics..."):
                    data = get_analytics(
                        api_base,
                        analytics_code,
                    )

                st.success("Analytics loaded")

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric(
                        "Total Clicks",
                        data.get("totalClicks", 0),
                    )

                with col2:
                    st.metric(
                        "Short Code",
                        data.get("shortCode", ""),
                    )

                with col3:
                    st.metric(
                        "Last Access",
                        str(
                            data.get("lastAccessedAt")
                            or "Never"
                        ),
                    )

                st.write("**Created at:**")
                st.write(data.get("createdAt", ""))

                with st.expander("Full analytics response"):
                    st.json(data)

            except httpx.HTTPError as exc:
                st.error(f"API connection error: {exc}")

            except ValueError as exc:
                st.error(str(exc))
