"""Optional browser smoke: pip install playwright; use installed Microsoft Edge.

Run the real Streamlit server on localhost:8501 first. This script only reads UI;
approval/export mutations are covered with isolated storage in test_ui_real.py.
"""
from pathlib import Path
import argparse

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ml", action="store_true", help="Exercise the locally trained ML forecaster")
    parser.add_argument("--url", default="http://localhost:8501")
    parser.add_argument("--screenshots-dir", type=Path, default=Path(".pytest_cache/ui-screenshots"))
    args = parser.parse_args()
    screenshots = args.screenshots_dir / ("ml" if args.ml else "statistical")
    screenshots.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url, wait_until="networkidle")
        if args.ml:
            page.get_by_test_id("stSidebar").get_by_role("combobox").first.click()
            page.get_by_role("option", name="ML — обученный бустинг", exact=True).click()
        page.get_by_role("button", name="Рассчитать", exact=True).click()
        expect(page.get_by_role("tab", name="Заказ", exact=True)).to_be_visible(timeout=60000)
        expect(page.get_by_text("реальные данные Excel", exact=False)).to_be_visible()
        expect(page.get_by_role("button", name="Утвердить заказ поставщика")).to_be_visible(timeout=30000)
        expect(page.get_by_role("tabpanel").filter(visible=True).get_by_test_id("stDataFrame").first).to_be_visible()
        if args.ml:
            expect(page.get_by_text("Прогноз: обученный ML", exact=False)).to_be_visible()
        page.screenshot(path=str(screenshots / "order-desktop.png"), full_page=True)
        expect(page.get_by_role("tab")).to_have_count(6)
        for label in ("Товар", "Проверки", "Сравнение с менеджером", "Разовые заказы", "Ассистент"):
            page.get_by_role("tab", name=label, exact=True).click()
            expect(page.get_by_role("tabpanel").filter(visible=True)).to_be_visible()
            assert page.get_by_test_id("stException").count() == 0
        panel = page.get_by_role("tabpanel").filter(visible=True)
        page.get_by_role("textbox", name="Ваш вопрос", exact=True).fill("IEK заказ")
        page.get_by_role("button", name="Спросить", exact=True).click()
        expect(page.get_by_text("Источник:", exact=False)).to_be_visible(timeout=30000)
        page.get_by_text("На чем основан ответ:", exact=False).click()
        expect(panel.get_by_test_id("stDataFrame").first).to_be_visible()
        expect(panel.get_by_text("Жизненный цикл ассортимента", exact=True)).to_be_visible()
        expect(panel.get_by_text("Смена моделей", exact=True)).to_be_visible()
        assert page.get_by_test_id("stException").count() == 0
        page.get_by_text("Источник:", exact=False).scroll_into_view_if_needed()
        page.screenshot(path=str(screenshots / "assistant-desktop.png"), full_page=True)
        page.get_by_role("tab", name="Товар", exact=True).click()
        panel = page.get_by_role("tabpanel").filter(visible=True)
        panel.get_by_role("combobox").click()
        panel.get_by_role("combobox").fill("130200305_")
        page.get_by_role("option").filter(has_text="130200305_").first.click()
        expect(panel.get_by_text("Отмеченные разовые строки", exact=True)).to_be_visible(timeout=20000)
        page.screenshot(path=str(screenshots / "loop-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.get_by_role("tab", name="Заказ", exact=True).click()
        expect(page.get_by_role("tab", name="Заказ", exact=True)).to_be_visible()
        page.screenshot(path=str(screenshots / "order-mobile.png"), full_page=True)
        assert not errors, errors
        browser.close()
    print(f"Browser smoke passed; screenshots: {screenshots}")


if __name__ == "__main__":
    main()
