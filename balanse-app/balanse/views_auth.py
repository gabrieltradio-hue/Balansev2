"""The screens before the app opens: sign in, create an account (owner or staff with a join code),
confirm the email with an emailed code, and reset a forgotten password.

Design: the whole screen navy, the balance-scale logo as a faint watermark in the lower right,
and one compact panel in the middle.
"""
from __future__ import annotations

import os
from html import escape
from typing import Optional
from urllib.parse import quote

import streamlit as st

from . import session, ui
from .auth import AuthError, Member

VIEW = "auth_view"          # sign_in | sign_up | confirm | business | forgot | reset

# The logo outline as the page background. A background image, because Streamlit's page wrappers stop a
# "position: fixed" element from staying in the corner.
WATERMARK = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-2 0 68 56"><g fill="none" stroke="#FFFFFF" stroke-opacity="0.11" stroke-width="1.8" stroke-linecap="round">'
             '<path d="M6 14H58"/><path d="M32 8V50"/><path d="M18 51H46"/><path d="M6 14L2 33M6 14L22 33M58 14L42 33M58 14L62 33"/>'
             '<path d="M2 33Q12 45 22 33M42 33Q52 45 62 33"/></g><g fill="none" stroke="#FFFFFF" stroke-opacity="0.11" stroke-width="1.4">'
             '<rect x="4" y="24" width="8" height="8" rx="1.6"/><rect x="13" y="24" width="8" height="8" rx="1.6"/>'
             '<rect x="43" y="24" width="8" height="8" rx="1.6"/><rect x="52" y="24" width="8" height="8" rx="1.6"/></g>'
             '<circle cx="32" cy="8" r="4.2" fill="none" stroke="#FFFFFF" stroke-opacity="0.11" stroke-width="1.6"/></svg>')
WATERMARK_URL = "data:image/svg+xml;charset=utf-8," + quote(WATERMARK)

# No asterisks in this stylesheet: st.markdown would read them as italics and break the rules.
CSS = """
<style>
.stApp { background:#0F1B2D url("WATERMARK_URL") no-repeat right 5vw bottom 6vh / 260px auto !important; }
[data-testid="stAppViewContainer"], [data-testid="stMain"] { background:transparent !important; }
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], header[data-testid="stHeader"] { display:none !important; }
[data-testid="stMain"] .block-container { max-width:340px !important; padding:9vh 16px 6vh !important; }
.bal-auth-brand { display:flex; align-items:center; justify-content:center; gap:8px; color:#FFFFFF; font-weight:700; font-size:18px; letter-spacing:.01em; margin:0 0 6px; }
.bal-auth-brand .mark { width:32px; height:28px; }
.st-key-auth-card { background:#16253C; border:1px solid #26385A; border-radius:10px; padding:20px 20px 16px; gap:.55rem; position:relative; z-index:1; }
.st-key-auth-card h2.bal-auth-title { font-size:19px !important; font-weight:600 !important; color:#FFFFFF !important; margin:0 !important; padding:0 !important; letter-spacing:0; }
.st-key-auth-card h2.bal-auth-title::after { display:none !important; }
.st-key-auth-card .bal-auth-sub { font-size:12.5px !important; color:#9FB0C6; margin:2px 0 6px; line-height:1.45; }
.bal-auth-sub b { color:#E6ECF4; font-weight:500; }
.st-key-auth-card label, .st-key-auth-card label p, .st-key-auth-card [data-testid="stWidgetLabel"] p { color:#B7C4D6 !important; font-size:12px !important; font-weight:500 !important; }
.st-key-auth-card [data-testid="stTextInputRootElement"], .st-key-auth-card [data-baseweb="input"], .st-key-auth-card [data-baseweb="base-input"] { background:#0F1B2D !important; border-color:#2E4266 !important; }
.st-key-auth-card [data-testid="stTextInputRootElement"]:focus-within { border-color:#5B8DEF !important; box-shadow:0 0 0 2px rgba(47,111,224,.25); }
.st-key-auth-card input { color:#E6ECF4 !important; -webkit-text-fill-color:#E6ECF4 !important; font-size:13px !important; caret-color:#E6ECF4; }
.st-key-auth-card input:-webkit-autofill, .st-key-auth-card input:-webkit-autofill:focus { -webkit-box-shadow:0 0 0 1000px #0F1B2D inset !important; box-shadow:0 0 0 1000px #0F1B2D inset !important; -webkit-text-fill-color:#E6ECF4 !important; caret-color:#E6ECF4; }
.st-key-auth-card [data-testid="InputInstructions"] { display:none !important; }
.st-key-auth-card input::placeholder { color:#6F819E !important; -webkit-text-fill-color:#6F819E !important; }
.st-key-auth-card [data-testid="stTextInputRootElement"] button, .st-key-auth-card [data-testid="stTextInputRootElement"] svg { color:#8FA3C0 !important; fill:#8FA3C0 !important; background:transparent !important; }
.st-key-auth-card [data-testid="stForm"] { background:transparent !important; border:0 !important; padding:0 !important; }
.st-key-auth-card .stFormSubmitButton > button, .st-key-auth-card .stButton > button[kind="primary"] { background:#2F6FE0 !important; border-color:#2F6FE0 !important; color:#FFFFFF !important; min-height:2.3rem; margin-top:4px; }
.st-key-auth-card .stFormSubmitButton > button:hover, .st-key-auth-card .stButton > button[kind="primary"]:hover { background:#2861C7 !important; border-color:#2861C7 !important; }
.st-key-auth-card .stFormSubmitButton > button p, .st-key-auth-card .stButton > button[kind="primary"] p { color:#FFFFFF !important; }
.st-key-auth-card .stButton > button[kind="tertiary"], .st-key-auth-card .stButton > button[kind="tertiary"] p { color:#8FB6F7 !important; font-size:12px !important; font-weight:500; }
.st-key-auth-card .stButton > button[kind="tertiary"]:hover p { text-decoration:underline; }
.st-key-auth-card [data-testid="stButtonGroup"] { width:100%; }
.st-key-auth-card [data-testid="stButtonGroup"] button { flex:1 1 0; background:#0F1B2D !important; border-color:#2E4266 !important; min-height:2rem; }
.st-key-auth-card [data-testid="stButtonGroup"] button p { color:#B7C4D6 !important; font-size:12px !important; }
.st-key-auth-card [data-testid="stButtonGroup"] button[aria-checked="true"] { background:#2F6FE0 !important; border-color:#2F6FE0 !important; }
.st-key-auth-card [data-testid="stButtonGroup"] button[aria-checked="true"] p { color:#FFFFFF !important; }
.st-key-auth-card [data-testid="stButtonGroup"] button p { white-space:nowrap; }
.st-key-auth-links { flex-direction:row !important; justify-content:center; gap:4px !important; flex-wrap:wrap; }
.bal-auth-alt { text-align:center; font-size:12px; color:#9FB0C6; margin:4px 0 -8px; }
.bal-auth-err { font-size:12.5px; color:#F5C2B6; background:rgba(181,69,47,.18); border:1px solid rgba(181,69,47,.45); border-radius:6px; padding:8px 10px; line-height:1.4; }
.bal-auth-ok { font-size:12.5px; color:#BFE3D2; background:rgba(91,122,134,.22); border:1px solid rgba(91,122,134,.5); border-radius:6px; padding:8px 10px; line-height:1.4; }
.bal-auth-dev { font-size:11.5px; color:#F3D48B; background:rgba(243,212,139,.08); border:1px dashed rgba(243,212,139,.35); border-radius:6px; padding:7px 9px; line-height:1.4; }
.bal-auth-foot { text-align:center; font-size:11px; color:#6F819E; margin-top:4px; }
.bal-auth-setup { color:#C9D3E0; font-size:13px; line-height:1.55; }
.bal-auth-setup code { background:#0F1B2D; color:#E6ECF4; padding:1px 5px; border-radius:4px; }
</style>
"""


def _go(view: str) -> None:
    st.session_state[VIEW] = view
    st.session_state.pop("auth_error", None)


def _error(text: str) -> None:
    st.session_state["auth_error"] = text


def _header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<h2 class="bal-auth-title">{escape(title)}</h2>' + (f'<p class="bal-auth-sub">{subtitle}</p>' if subtitle else ""),
                unsafe_allow_html=True)
    if st.session_state.get("auth_error"):
        st.markdown(f'<div class="bal-auth-err">{escape(st.session_state["auth_error"])}</div>', unsafe_allow_html=True)
    if st.session_state.get("auth_notice"):
        st.markdown(f'<div class="bal-auth-ok">{escape(st.session_state.pop("auth_notice"))}</div>', unsafe_allow_html=True)


def _preview_code(email: str) -> None:
    """In preview mode nothing is emailed, so show the code that would have been sent."""
    backend = session.preview_backend()
    if backend is not None and backend.outbox.get((email or "").strip().lower()):
        st.markdown(f'<div class="bal-auth-dev">Preview mode: no email is sent. The code would be '
                    f'<b>{backend.outbox[email.strip().lower()]}</b>.</div>', unsafe_allow_html=True)


def _signed_in(found: Optional[Member]) -> None:
    """After a sign-in or a confirmed email: open the app, or ask to start or join a business first."""
    if found is None:
        _go("business")
    else:
        session.set_member(found)
        for key in (VIEW, "auth_error", "pending"):
            st.session_state.pop(key, None)
    st.rerun()


# ---------------------------------------------------------------- the screens
def _sign_in() -> None:
    _header("Sign in", "Welcome back. Use your Balanse account.")
    with st.form("auth-sign-in", border=False):
        email = st.text_input("Email", key="si-email", placeholder="you@example.com", autocomplete="email")
        password = st.text_input("Password", type="password", key="si-password", autocomplete="current-password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)
    if submitted:
        try:
            _signed_in(session.accounts().sign_in(email, password))
        except AuthError as problem:
            _error(str(problem))
            st.rerun()
    with st.container(key="auth-links"):
        # resetting a password needs email; BALANSE_EMAIL=off hides it while the project sends no email
        if os.environ.get("BALANSE_EMAIL", "on").strip().lower() != "off":
            if st.button("Forgot password?", key="to-forgot", type="tertiary"):
                st.session_state["reset_email"] = email
                _go("forgot"); st.rerun()
        if st.button("Create an account", key="to-sign-up", type="tertiary"):
            _go("sign_up"); st.rerun()


def _business_fields(prefix: str) -> tuple[str, str, str]:
    """Owner or staff, and the business name or join code. Returns (kind, value, display name)."""
    kind = st.segmented_control("Account type", ["I'm the owner", "I have a code"], default="I'm the owner",
                                key=f"{prefix}-kind", label_visibility="collapsed") or "I'm the owner"
    if kind == "I'm the owner":
        value = st.text_input("Business name", key=f"{prefix}-business", placeholder="e.g. Hife Store", max_chars=80,
                              autocomplete="organization")
    else:
        value = st.text_input("Join code", key=f"{prefix}-code", placeholder="8 letters and numbers from the owner", max_chars=12,
                              autocomplete="off")
    name = st.text_input("Your name", key=f"{prefix}-name", placeholder="e.g. Gabriel", max_chars=60, autocomplete="name")
    return ("owner" if kind == "I'm the owner" else "staff"), value, name


def _finish(kind: str, value: str, name: str) -> None:
    accounts = session.accounts()
    found = accounts.create_business(value, name) if kind == "owner" else accounts.join_business(value, name)
    _signed_in(found)


def _sign_up() -> None:
    _header("Create an account", "Start a business, or join one with a code from its owner.")
    kind, value, name = _business_fields("su")
    with st.form("auth-sign-up", border=False):
        email = st.text_input("Email", key="su-email", placeholder="you@example.com", autocomplete="email")
        password = st.text_input("Password", type="password", key="su-password", placeholder="At least 8 characters", autocomplete="new-password")
        again = st.text_input("Password again", type="password", key="su-password2", autocomplete="new-password")
        submitted = st.form_submit_button("Create account", use_container_width=True)
    if submitted:
        try:
            if not value.strip():
                raise AuthError("Enter the business name." if kind == "owner" else "Enter the join code from the business owner.")
            if password != again:
                raise AuthError("The two passwords are not the same.")
            needs_code = session.accounts().sign_up(email, password, name)
            st.session_state["pending"] = {"email": email.strip().lower(), "kind": kind, "value": value, "name": name}
            if needs_code:
                _go("confirm"); st.rerun()
            _finish(kind, value, name)
        except AuthError as problem:
            _error(str(problem)); st.rerun()
    with st.container(key="auth-links"):
        if st.button("I already have an account", key="to-sign-in", type="tertiary"):
            _go("sign_in"); st.rerun()


def _confirm() -> None:
    pending = st.session_state.get("pending") or {}
    email = pending.get("email", "")
    _header("Check your email", f"We sent a code to <b>{escape(email)}</b>. Enter it to confirm the address.")
    _preview_code(email)
    with st.form("auth-confirm", border=False):
        code = st.text_input("Code", key="cf-code", placeholder="The code from the email", max_chars=10)
        submitted = st.form_submit_button("Confirm", use_container_width=True)
    if submitted:
        try:
            session.accounts().confirm_email(email, code)
            _finish(pending.get("kind", "owner"), pending.get("value", ""), pending.get("name", ""))
        except AuthError as problem:
            _error(str(problem)); st.rerun()
    with st.container(key="auth-links"):
        if st.button("Back to sign in", key="cf-back", type="tertiary"):
            _go("sign_in"); st.rerun()


def _business() -> None:
    """Signed in, but not part of a business yet (for example the app was closed after confirming the email)."""
    _header("Set up your business", "Your account is ready. Start a business, or join one with a code from its owner.")
    kind, value, name = _business_fields("bz")
    if st.button("Continue", key="bz-go", type="primary", use_container_width=True):
        try:
            _finish(kind, value, name)
        except AuthError as problem:
            _error(str(problem)); st.rerun()
    with st.container(key="auth-links"):
        if st.button("Sign out", key="bz-out", type="tertiary"):
            session.sign_out(); st.rerun()


def _forgot() -> None:
    _header("Reset your password", "Enter your account's email. We will send you a code.")
    with st.form("auth-forgot", border=False):
        email = st.text_input("Email", key="fg-email", value=st.session_state.get("reset_email", ""), placeholder="you@example.com")
        submitted = st.form_submit_button("Send code", use_container_width=True)
    if submitted:
        try:
            session.accounts().send_reset_code(email)
            st.session_state["reset_email"] = email.strip().lower()
            _go("reset"); st.rerun()
        except AuthError as problem:
            _error(str(problem)); st.rerun()
    with st.container(key="auth-links"):
        if st.button("Back to sign in", key="fg-back", type="tertiary"):
            _go("sign_in"); st.rerun()


def _reset() -> None:
    email = st.session_state.get("reset_email", "")
    _header("Reset your password", f"If <b>{escape(email)}</b> has an account, a code is on its way. "
                                   "Enter it with your new password.")
    _preview_code(email)
    with st.form("auth-reset", border=False):
        code = st.text_input("Code", key="rs-code", placeholder="The code from the email", max_chars=10)
        password = st.text_input("New password", type="password", key="rs-password", placeholder="At least 8 characters", autocomplete="new-password")
        again = st.text_input("New password again", type="password", key="rs-password2", autocomplete="new-password")
        submitted = st.form_submit_button("Save new password", use_container_width=True)
    if submitted:
        try:
            if password != again:
                raise AuthError("The two passwords are not the same.")
            _signed_in(session.accounts().reset_password(email, code, password))
        except AuthError as problem:
            _error(str(problem)); st.rerun()
    with st.container(key="auth-links"):
        if st.button("Send a new code", key="rs-again", type="tertiary"):
            try:
                session.accounts().send_reset_code(email)
                st.session_state["auth_notice"] = "A new code is on its way."
            except AuthError as problem:
                _error(str(problem))
            st.rerun()
        if st.button("Back to sign in", key="rs-back", type="tertiary"):
            _go("sign_in"); st.rerun()


def _not_set_up() -> None:
    _header("Balanse is not connected yet")
    st.markdown(f'<div class="bal-auth-setup">{escape(session.setup_problem())}<br><br>'
                'Signing in needs the online database. Add the project address and its public key to the '
                '<code>.env</code> file next to the app, then open Balanse again.</div>', unsafe_allow_html=True)


SCREENS = {"sign_in": _sign_in, "sign_up": _sign_up, "confirm": _confirm, "business": _business, "forgot": _forgot, "reset": _reset}


def gate() -> Optional[Member]:
    """The signed-in person, or None after drawing the sign-in screens (the app then shows nothing else)."""
    if session.mode() == "local":
        return session.member()
    if session.member() is not None:
        return session.member()
    st.markdown(ui.CSS + CSS.replace("WATERMARK_URL", WATERMARK_URL), unsafe_allow_html=True)
    st.markdown(f'<div class="bal-auth-brand">{ui.BRAND_SVG}<span>BALANSE</span></div>', unsafe_allow_html=True)
    with st.container(key="auth-card"):
        if session.mode() == "unconfigured":
            _not_set_up()
        else:
            try:
                SCREENS.get(st.session_state.get(VIEW, "sign_in"), _sign_in)()
            except AuthError as problem:                     # no internet when connecting
                st.markdown(f'<div class="bal-auth-err">{escape(str(problem))}</div>', unsafe_allow_html=True)
    st.markdown('<div class="bal-auth-foot">Your data is private to your business account.</div>', unsafe_allow_html=True)
    return None
