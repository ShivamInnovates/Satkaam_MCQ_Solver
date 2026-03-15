from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
import time
import sys

opts = Options()
opts.binary_location = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
# opts.add_argument("--headless=new")
driver = webdriver.Chrome(options=opts)

driver.get("https://forms.gle/yVK962ZSBb92gfKaA")
time.sleep(5)
blocks = driver.find_elements(By.CSS_SELECTOR, "div.Qr7Oae")
print("Blocks Qr7Oae:", len(blocks))
blocks2 = driver.find_elements(By.CSS_SELECTOR, "div[data-params]")
print("Blocks data-params:", len(blocks2))
blocks3 = driver.find_elements(By.CSS_SELECTOR, "div.freebirdFormviewerComponentsQuestionBaseRoot")
print("Blocks freebird:", len(blocks3))
driver.quit()
