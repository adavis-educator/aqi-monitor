# AQI Monitor for Mt. Tamalpais School

Automated air quality monitoring system that checks the school's PurpleAir sensor and sends email alerts when AQI crosses specified thresholds.

## Features

- Checks PurpleAir sensor every 15 minutes during school hours (7am-3pm PT, weekdays)
- Calculates AQI using US EPA correction formula (matches PurpleAir widget display)
- Sends email alerts when AQI crosses thresholds:
  - **AQI 100** (Unhealthy for Sensitive Groups): alerts attendance@mttam.org
  - **AQI 150** (Unhealthy): alerts attendance + admin staff
- Only alerts once per threshold crossing (not every 15 minutes while above)
- Sends "all clear" alert when AQI drops back below each threshold

## Setup Instructions

### 1. Create a GitHub Gist for State Storage

The monitor needs to remember which alerts have been sent. We use a GitHub Gist for this:

1. Go to https://gist.github.com/
2. Create a new **secret** gist
3. Filename: `aqi_state.json`
4. Content: `{"alerted_thresholds": []}`
5. Click "Create secret gist"
6. Copy the Gist ID from the URL (the long string after your username)

### 2. Create a GitHub Personal Access Token

1. Go to https://github.com/settings/tokens?type=beta
2. Click "Generate new token"
3. Name: `AQI Monitor Gist Access`
4. Expiration: Choose an appropriate duration
5. Repository access: Select "Only select repositories" → select this repo
6. Permissions: Under "Account permissions", set "Gists" to "Read and write"
7. Generate token and copy it

### 3. Set Up Gmail App Password

1. Go to https://myaccount.google.com/security
2. Ensure 2-Step Verification is enabled
3. Go to https://myaccount.google.com/apppasswords
4. Select "Mail" and your device
5. Click "Generate"
6. Copy the 16-character password (no spaces)

### 4. Configure GitHub Repository Secrets

Go to your repository → Settings → Secrets and variables → Actions → New repository secret

Add these secrets:

| Secret Name | Value |
|------------|-------|
| `PURPLEAIR_API_KEY` | Your PurpleAir API key |
| `GMAIL_ADDRESS` | The Gmail address to send from |
| `GMAIL_APP_PASSWORD` | The 16-character app password |
| `GIST_TOKEN` | Your GitHub personal access token |
| `GIST_ID` | The ID of your state gist |

### 5. Enable GitHub Actions

The workflow will automatically run every 15 minutes. You can also trigger it manually from the Actions tab.

## Local Testing

```bash
# Set environment variables
export PURPLEAIR_API_KEY="your-key"
export GMAIL_ADDRESS="your-email@gmail.com"
export GMAIL_APP_PASSWORD="your-app-password"
export GITHUB_TOKEN="your-github-token"
export GIST_ID="your-gist-id"

# Run with --force to bypass school hours check
python aqi_monitor.py --force
```

## AQI Categories

| AQI | Category | Color |
|-----|----------|-------|
| 0-50 | Good | Green |
| 51-100 | Moderate | Yellow |
| 101-150 | Unhealthy for Sensitive Groups | Orange |
| 151-200 | Unhealthy | Red |
| 201-300 | Very Unhealthy | Purple |
| 301-500 | Hazardous | Maroon |

## Sensor Information

- **Sensor ID**: 254241
- **Name**: Mount Tamalpais School
- **Live Data**: https://map.purpleair.com/?select=254241
