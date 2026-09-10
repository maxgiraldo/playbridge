"""Headless Chrome walkthrough of the contract table."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

SHOTS = Path("/tmp/minibridge-ui")
SHOTS.mkdir(parents=True, exist_ok=True)


def shot(driver: webdriver.Chrome, name: str) -> None:
    path = SHOTS / f"{name}.png"
    driver.save_screenshot(str(path))
    print("shot", path)


def post(path: str, body: dict) -> None:
    req = urllib.request.Request(
        f"http://127.0.0.1:8000{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req).read()


def main() -> None:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,900")
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 10)
    try:
        post("/api/games/table/reset", {"seed": 3, "new_match": True, "rules": "bridge"})
        driver.get("http://127.0.0.1:8000/")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-call], [data-trump], .status")))
        shot(driver, "40-auction")
        if driver.find_elements(By.CSS_SELECTOR, "[data-call='P']"):
            driver.find_element(By.CSS_SELECTOR, "[data-call='P']").click()
        for index in range(8):
            wait.until(
                lambda d: d.find_elements(By.CSS_SELECTOR, ".card.legal, [data-call], #next-deal")
            )
            if driver.find_elements(By.ID, "next-deal"):
                shot(driver, "43-over")
                break
            calls = [el for el in driver.find_elements(By.CSS_SELECTOR, "[data-call='P']") if el.is_enabled()]
            if calls:
                driver.execute_script("arguments[0].click()", calls[0])
                shot(driver, f"41-call-{index + 1}")
                continue
            cards = driver.find_elements(By.CSS_SELECTOR, ".card.legal")
            if cards:
                driver.execute_script("arguments[0].click()", cards[0])
                shot(driver, f"42-trick-{index + 1}")
        print("ok")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
