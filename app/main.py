from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from app.core.logger import logger, setup_logger
from app.infrastructure.browser import PlaywrightBrowserManager
from app.infrastructure.llm import OpenAILLMClient
from app.infrastructure.storage import BundleResultStore
from app.infrastructure.storage.checkpoint import CheckpointManager
from app.infrastructure.storage.excel_exporter import (
    export_hypothesis_to_excel,
    export_judgment_to_excel,
)
from app.services.hypothesis_service import HypothesisService
from app.services.judgment_service import JudgmentService
from app.services.product_service import ProductService

OUTPUT_DIR = Path("output") / "bundling"


async def run_generate(url: str) -> None:
    """Mode A: Generate hypotheses for a product URL."""
    logger.info("=== Mode A: Hypothesis Generation ===")
    logger.info("Product URL: {}", url)

    browser = PlaywrightBrowserManager()
    try:
        await browser.start()
        llm = OpenAILLMClient()
        product_service = ProductService(browser)
        hypothesis_service = HypothesisService(llm)

        logger.info("Scraping product...")
        product = await product_service.get_product(url)
        logger.info("Scraped: {}", product.title)

        logger.info("Generating hypotheses via GPT...")
        result = await hypothesis_service.generate(product)

        store = BundleResultStore()
        json_path = store.save_hypothesis(result)
        excel_path = export_hypothesis_to_excel(result, OUTPUT_DIR / json_path.with_suffix(".xlsx").name)
        logger.info("Done! Results saved to: {}", json_path)
        print(f"\nJSON:  {json_path}")
        print(f"Excel: {excel_path}")
        print(f"Total directions: {len(result.directions)}")

    finally:
        await browser.stop()


async def run_judge(a_url: str, b_urls: list[str]) -> None:
    """Mode B: Judge B-candidate hypotheses with real product data."""
    logger.info("=== Mode B: Hypothesis Judgment ===")
    logger.info("A product: {}", a_url)
    logger.info("B products: {}", b_urls)

    browser = PlaywrightBrowserManager()
    try:
        await browser.start()
        llm = OpenAILLMClient()
        product_service = ProductService(browser)
        judgment_service = JudgmentService(llm)

        logger.info("Scraping A product...")
        product_a = await product_service.get_product(a_url)
        logger.info("A: {}", product_a.title)

        products_b = []
        for url in b_urls:
            logger.info("Scraping B product: {}", url)
            pb = await product_service.get_product(url)
            products_b.append(pb)
            logger.info("B: {}", pb.title)

        logger.info("Running judgment via GPT...")
        result = await judgment_service.judge(product_a, products_b, [])

        store = BundleResultStore()
        json_path = store.save_judgment(result, product_a=product_a, products_b=products_b)
        excel_path = export_judgment_to_excel(result, OUTPUT_DIR / json_path.with_suffix(".xlsx").name)
        logger.info("Done! Judgment saved to: {}", json_path)
        print(f"\nJSON:  {json_path}")
        print(f"Excel: {excel_path}")
        print(f"Final grade: {result.final_grade}")

    finally:
        await browser.stop()


async def run_batch(input_file: str, resume_batch_id: str | None = None) -> None:
    """Batch mode: process multiple product URLs with checkpoint/resume."""
    if resume_batch_id:
        logger.info("=== Batch Mode: Resuming batch {} ===", resume_batch_id)
        cp = CheckpointManager.load(resume_batch_id)
    else:
        urls = Path(input_file).read_text(encoding="utf-8").strip().splitlines()
        urls = [u.strip() for u in urls if u.strip() and not u.strip().startswith("#")]
        batch_id = datetime.now().strftime("batch_%Y%m%d_%H%M%S")
        logger.info("=== Batch Mode: Starting new batch {} with {} URLs ===", batch_id, len(urls))
        cp = CheckpointManager(batch_id)
        cp.add_urls(urls)

    pending = cp.get_retryable() if resume_batch_id else cp.get_pending()
    if not pending:
        logger.info("All URLs processed. {}", cp.summary)
        print(f"\nAll done! {cp.summary}")
        return

    browser = PlaywrightBrowserManager()
    store = BundleResultStore()
    try:
        await browser.start()
        llm = OpenAILLMClient()
        product_service = ProductService(browser)
        hypothesis_service = HypothesisService(llm)

        for i, url in enumerate(pending):
            logger.info("[{}/{}] Processing: {}", i + 1, len(pending), url)
            try:
                if resume_batch_id:
                    cp.mark_pending(url)
                product = await product_service.get_product(url)
                result = await hypothesis_service.generate(product)

                json_path = store.save_hypothesis(result)
                export_hypothesis_to_excel(result, OUTPUT_DIR / json_path.with_suffix(".xlsx").name)
                cp.mark_done(url, str(json_path))
                logger.info("[{}/{}] Done: {} - {} directions", i + 1, len(pending),
                            product.title[:40], len(result.directions))
            except Exception as e:
                logger.error("[{}/{}] Failed: {} - {}", i + 1, len(pending), url, e)
                cp.mark_failed(url, str(e))

    finally:
        await browser.stop()

    print(f"\nBatch complete! {cp.summary}")
    print(f"Checkpoint: {cp._path}")
    if cp.stats["pending"] > 0 or cp.stats["failed"] > 0:
        print(f"To resume: python -m app.main --mode batch --resume {cp._state['batch_id']}")


def main() -> None:
    setup_logger()

    parser = argparse.ArgumentParser(description="A+B Bundling System")
    parser.add_argument("--mode", choices=["generate", "judge", "batch"], required=True,
                        help="generate=指令A, judge=指令B, batch=批量处理")
    parser.add_argument("--url", help="Product URL (for generate mode)")
    parser.add_argument("--a-url", help="Product A URL (for judge mode)")
    parser.add_argument("--b-urls", nargs="+", help="Product B URL(s) (for judge mode)")
    parser.add_argument("--input", help="URL list file (for batch mode)")
    parser.add_argument("--resume", help="Batch ID to resume (for batch mode)")

    args = parser.parse_args()

    if args.mode == "generate":
        if not args.url:
            parser.error("--url is required for generate mode")
        asyncio.run(run_generate(args.url))
    elif args.mode == "judge":
        if not args.a_url or not args.b_urls:
            parser.error("--a-url and --b-urls are required for judge mode")
        asyncio.run(run_judge(args.a_url, args.b_urls))
    elif args.mode == "batch":
        if not args.input and not args.resume:
            parser.error("--input or --resume is required for batch mode")
        asyncio.run(run_batch(args.input, args.resume))


if __name__ == "__main__":
    main()
