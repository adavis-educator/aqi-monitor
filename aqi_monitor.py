#!/usr/bin/env python3
"""
Air Quality Monitor for PurpleAir Sensors
Checks sensor readings, calculates AQI, and sends email alerts when thresholds are crossed.
"""

import os
import sys
import json
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Tuple, List

# Configuration
SENSOR_ID = 254241
SENSOR_URL = f"https://map.purpleair.com/?select={SENSOR_ID}"

# Environment variables
PURPLEAIR_API_KEY = os.environ.get("PURPLEAIR_API_KEY", "")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GIST_ID = os.environ.get("GIST_ID", "")

# AQI thresholds and alert recipients
THRESHOLDS = {
    100: {
        "name": "Unhealthy for Sensitive Groups",
        "recipients": ["attendance@mttam.org"],
    },
    150: {
        "name": "Unhealthy",
        "recipients": [
            "attendance@mttam.org",
            "adavis@mttam.org",
            "nwilsey@mttam.org",
            "mandrews@mttam.org",
        ],
    },
}

# School hours (Pacific Time)
TIMEZONE = ZoneInfo("America/Los_Angeles")
SCHOOL_START_HOUR = 7   # 7 AM
SCHOOL_END_HOUR = 15    # 3 PM
SCHOOL_DAYS = [0, 1, 2, 3, 4]  # Monday=0 through Friday=4

# EPA AQI breakpoints for PM2.5
AQI_BREAKPOINTS = [
    (0.0, 12.0, 0, 50),
    (12.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 150.4, 151, 200),
    (150.5, 250.4, 201, 300),
    (250.5, 350.4, 301, 400),
    (350.5, 500.4, 401, 500),
]


def is_school_hours() -> bool:
    """Check if current time is within school hours (7am-3pm PT, weekdays)."""
    now = datetime.now(TIMEZONE)
    is_weekday = now.weekday() in SCHOOL_DAYS
    is_school_time = SCHOOL_START_HOUR <= now.hour < SCHOOL_END_HOUR
    return is_weekday and is_school_time


def calculate_aqi(pm25: float) -> int:
    """Calculate AQI from PM2.5 concentration using EPA breakpoints."""
    pm25 = round(pm25, 1)

    if pm25 < 0:
        return 0
    if pm25 > 500.4:
        return 500

    for bp_lo, bp_hi, aqi_lo, aqi_hi in AQI_BREAKPOINTS:
        if bp_lo <= pm25 <= bp_hi:
            aqi = ((aqi_hi - aqi_lo) / (bp_hi - bp_lo)) * (pm25 - bp_lo) + aqi_lo
            return round(aqi)

    return 500


def apply_epa_correction(pm25_cf1: float, humidity: float) -> float:
    """Apply US EPA correction formula for PurpleAir sensors."""
    if pm25_cf1 <= 343:
        corrected = 0.52 * pm25_cf1 - 0.086 * humidity + 5.75
    else:
        corrected = 0.46 * pm25_cf1 + 3.93e-4 * (pm25_cf1 ** 2) + 2.97

    return max(0, corrected)


def get_sensor_data() -> Optional[dict]:
    """Fetch current sensor data from PurpleAir API."""
    if not PURPLEAIR_API_KEY:
        print("Error: PURPLEAIR_API_KEY not set")
        return None

    url = "https://api.purpleair.com/v1/sensors"
    headers = {"X-API-Key": PURPLEAIR_API_KEY}
    params = {
        "fields": "name,pm2.5_10minute_a,pm2.5_10minute_b,humidity,temperature",
        "show_only": SENSOR_ID,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        fields = data.get("fields", [])
        sensor_data = data.get("data", [])

        if not sensor_data:
            print(f"Error: Sensor {SENSOR_ID} not found")
            return None

        sensor = dict(zip(fields, sensor_data[0]))

        pm25_a = sensor.get("pm2.5_10minute_a")
        pm25_b = sensor.get("pm2.5_10minute_b")

        if pm25_a is None and pm25_b is None:
            print("Error: No PM2.5 data available")
            return None

        if pm25_a is not None and pm25_b is not None:
            pm25_cf1 = (pm25_a + pm25_b) / 2
        else:
            pm25_cf1 = pm25_a if pm25_a is not None else pm25_b

        return {
            "name": sensor.get("name", f"Sensor {SENSOR_ID}"),
            "pm25_cf1": pm25_cf1,
            "humidity": sensor.get("humidity", 50),
            "temperature": sensor.get("temperature"),
        }

    except requests.exceptions.RequestException as e:
        print(f"Error fetching sensor data: {e}")
        return None


def get_aqi_category(aqi: int) -> str:
    """Return AQI category name."""
    if aqi <= 50:
        return "Good"
    elif aqi <= 100:
        return "Moderate"
    elif aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    elif aqi <= 200:
        return "Unhealthy"
    elif aqi <= 300:
        return "Very Unhealthy"
    else:
        return "Hazardous"


# --- State Management (GitHub Gist) ---

def get_state() -> dict:
    """Retrieve alert state from GitHub Gist."""
    if not GITHUB_TOKEN or not GIST_ID:
        print("Warning: GitHub credentials not set, using empty state")
        return {"alerted_thresholds": []}

    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        gist = response.json()
        content = gist["files"]["aqi_state.json"]["content"]
        return json.loads(content)

    except Exception as e:
        print(f"Error reading state: {e}")
        return {"alerted_thresholds": []}


def save_state(state: dict) -> bool:
    """Save alert state to GitHub Gist."""
    if not GITHUB_TOKEN or not GIST_ID:
        print("Warning: GitHub credentials not set, state not saved")
        return False

    try:
        url = f"https://api.github.com/gists/{GIST_ID}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        payload = {
            "files": {
                "aqi_state.json": {
                    "content": json.dumps(state, indent=2)
                }
            }
        }
        response = requests.patch(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return True

    except Exception as e:
        print(f"Error saving state: {e}")
        return False


# --- Email Alerts ---

def send_email(recipients: List[str], subject: str, body_html: str) -> bool:
    """Send email via Gmail SMTP."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("Warning: Gmail credentials not set, email not sent")
        print(f"Would send to: {recipients}")
        print(f"Subject: {subject}")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = ", ".join(recipients)

        # Plain text version
        body_text = body_html.replace("<br>", "\n").replace("</p>", "\n")
        import re
        body_text = re.sub(r"<[^>]+>", "", body_text)

        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, recipients, msg.as_string())

        print(f"Email sent to: {recipients}")
        return True

    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def send_threshold_alert(aqi: int, threshold: int, direction: str, sensor_name: str) -> bool:
    """Send alert email when threshold is crossed."""
    threshold_info = THRESHOLDS.get(threshold, {})
    recipients = threshold_info.get("recipients", [])
    threshold_name = threshold_info.get("name", f"AQI {threshold}")

    if not recipients:
        return False

    now = datetime.now(TIMEZONE)
    timestamp = now.strftime("%B %d, %Y at %I:%M %p PT")

    if direction == "rising":
        subject = f"⚠️ Air Quality Alert: AQI has reached {aqi} at {sensor_name}"
        action = "risen above"
        color = "#dc3545" if threshold >= 150 else "#fd7e14"
    else:
        subject = f"✅ Air Quality Improving: AQI now {aqi} at {sensor_name}"
        action = "dropped below"
        color = "#28a745"

    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background-color: {color}; color: white; padding: 20px; text-align: center;">
            <h1 style="margin: 0;">Air Quality Alert</h1>
        </div>
        <div style="padding: 20px; background-color: #f8f9fa;">
            <h2 style="color: #333;">Current AQI: {aqi}</h2>
            <p style="font-size: 16px;">
                The air quality index has <strong>{action}</strong> the
                <strong>{threshold_name}</strong> threshold (AQI {threshold}).
            </p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; background: white;"><strong>Sensor</strong></td>
                    <td style="padding: 10px; border: 1px solid #ddd; background: white;">{sensor_name}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; background: white;"><strong>Current AQI</strong></td>
                    <td style="padding: 10px; border: 1px solid #ddd; background: white;">{aqi}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; background: white;"><strong>Category</strong></td>
                    <td style="padding: 10px; border: 1px solid #ddd; background: white;">{get_aqi_category(aqi)}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd; background: white;"><strong>Time</strong></td>
                    <td style="padding: 10px; border: 1px solid #ddd; background: white;">{timestamp}</td>
                </tr>
            </table>
            <p>
                <a href="{SENSOR_URL}" style="display: inline-block; background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                    View Live Sensor Data
                </a>
            </p>
        </div>
        <div style="padding: 15px; background-color: #e9ecef; font-size: 12px; color: #666;">
            <p>This is an automated alert from the Mt. Tamalpais School AQI Monitor.</p>
        </div>
    </body>
    </html>
    """

    return send_email(recipients, subject, body_html)


# --- Main Logic ---

def check_and_alert() -> Optional[dict]:
    """Main function: check sensor, evaluate thresholds, send alerts if needed."""
    now = datetime.now(TIMEZONE)
    print(f"AQI Monitor - {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("=" * 50)

    # Check school hours
    if not is_school_hours():
        print(f"Outside school hours (7am-3pm PT weekdays). Skipping check.")
        return None

    # Get sensor data
    data = get_sensor_data()
    if not data:
        return None

    # Calculate AQI
    pm25_corrected = apply_epa_correction(data["pm25_cf1"], data["humidity"])
    aqi = calculate_aqi(pm25_corrected)
    category = get_aqi_category(aqi)

    print(f"Sensor: {data['name']}")
    print(f"PM2.5 (EPA corrected): {pm25_corrected:.1f} μg/m³")
    print(f"AQI: {aqi} ({category})")
    print("-" * 50)

    # Get current state
    state = get_state()
    alerted = set(state.get("alerted_thresholds", []))

    # Check thresholds
    sorted_thresholds = sorted(THRESHOLDS.keys())
    alerts_sent = []

    for threshold in sorted_thresholds:
        if aqi >= threshold and threshold not in alerted:
            # Crossed above threshold - send alert
            print(f"🚨 Crossed ABOVE {threshold} threshold!")
            if send_threshold_alert(aqi, threshold, "rising", data["name"]):
                alerted.add(threshold)
                alerts_sent.append(f"Rising above {threshold}")

        elif aqi < threshold and threshold in alerted:
            # Dropped below threshold - send recovery alert
            print(f"✅ Dropped BELOW {threshold} threshold!")
            if send_threshold_alert(aqi, threshold, "falling", data["name"]):
                alerted.discard(threshold)
                alerts_sent.append(f"Falling below {threshold}")

    # Save updated state
    new_state = {
        "alerted_thresholds": list(alerted),
        "last_aqi": aqi,
        "last_check": now.isoformat(),
    }
    save_state(new_state)

    print("-" * 50)
    if alerts_sent:
        print(f"Alerts sent: {', '.join(alerts_sent)}")
    else:
        print("No threshold crossings - no alerts sent")

    print(f"Currently alerted thresholds: {list(alerted) or 'None'}")

    return {
        "aqi": aqi,
        "category": category,
        "alerts_sent": alerts_sent,
        "alerted_thresholds": list(alerted),
    }


if __name__ == "__main__":
    # Allow running outside school hours for testing with --force flag
    if "--force" in sys.argv:
        # Temporarily override school hours check
        original_check = is_school_hours
        is_school_hours = lambda: True
        result = check_and_alert()
        is_school_hours = original_check
    else:
        result = check_and_alert()

    sys.exit(0 if result is not None else 1)
