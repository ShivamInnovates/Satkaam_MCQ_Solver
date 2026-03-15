# Google Form Auto-Filler Bot 🤖

Automatically fills Google Forms using:
- **Selenium** → controls Chrome browser
- **Gemini API** → answers MCQ and open-ended questions
- **config.json** → your personal info (name, email, etc.)

---

## 📁 Project Structure

```
google_form_bot/
├── form_bot.py       ← Main script
├── config.json       ← YOUR personal info + Gemini API key
├── requirements.txt  ← Python dependencies
└── README.md
```

---

## ⚙️ Setup (One Time)

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Install Google Chrome
Make sure Google Chrome browser is installed on your system.
- Download: https://www.google.com/chrome/

### 3. Edit `config.json`
Open `config.json` and fill in:
- Your **personal details** (name, email, phone, etc.)
- Your **Gemini API key**

#### How to get a Gemini API key:
1. Go to https://aistudio.google.com/app/apikey
2. Click "Create API Key"
3. Copy and paste it into `config.json` in the `gemini_api_key` field

---

## ▶️ Usage

```bash
python3 form_bot.py <google_form_url>
```

### Examples:
```bash
python3 form_bot.py https://forms.gle/abcXYZ123
python3 form_bot.py "https://docs.google.com/forms/d/e/xxxxx/viewform"
```

---

## 🔄 How It Works

1. You run the script with the form URL
2. Chrome opens automatically and navigates to the form
3. For each question:
   - **Personal info fields** (Name, Email, Phone...) → filled from `config.json`
   - **MCQ / Checkbox / Dropdown** → Gemini API picks the best answer
   - **Short text questions** → Gemini API writes a brief answer
4. Bot handles multi-page forms automatically (clicks "Next")
5. Bot **stops before Submit** — browser stays open
6. **You review the answers**, then click Submit yourself ✅

---

## 🛠️ Customizing `config.json`

The bot matches form field labels to your `personal_info` keys.

For example, if a form has a field labeled **"Mobile Number"**, it looks for
`"Mobile Number"` in your config. Add as many keys as you need:

```json
"personal_info": {
  "Full Name": "Rahul Sharma",
  "Email": "rahul@example.com",
  "Roll Number": "21CS101",
  "Branch": "Computer Engineering"
}
```

The matching is **case-insensitive and partial** — so `"email address"` will
match your `"Email"` key automatically.

---

## ⚠️ Troubleshooting

| Problem | Fix |
|---|---|
| `Chrome not found` | Install Google Chrome from google.com/chrome |
| `API key error` | Check your Gemini API key in config.json |
| `Form not filling` | Some forms have CAPTCHAs — solve manually then let bot continue |
| Bot fills wrong field | Add the exact field label as a key in `personal_info` |

---

## 🔒 Privacy Note
- Your `config.json` contains personal data and your API key.
- **Never share** this file or commit it to GitHub.
- Add `config.json` to your `.gitignore` if using Git.
