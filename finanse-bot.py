import gspread
from google.oauth2.service_account import Credentials

creds = Credentials.from_service_account_file("creds.json",
    scopes = ["https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"])
gc = gspread.authorize(creds)
sh = gc.open("finanse-bot")
ws = sh.sheet1

ws.update_cell(1, 1, "Думан топ")

ws.append_row([430, "Проезд"])
ws.append_row([550, "Завтрак"])
ws.append_row([700, "Обед"])
print("Пошло, все работает")