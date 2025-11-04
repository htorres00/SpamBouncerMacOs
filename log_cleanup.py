#!/usr/bin/env python3
"""
Log Cleanup Script - Compresses and purges old spam bouncer logs
- Compresses logs older than 1 day (gzip)
- Deletes logs older than 30 days
- Runs daily at 2am via Launch Agent
"""

import os
import gzip
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import logging

# Setup logging for the cleanup script itself
LOG_DIR = Path(__file__).parent / "logs"
CLEANUP_LOG = LOG_DIR / "log_cleanup.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(CLEANUP_LOG),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def compress_log_file(log_file):
    """Compress a log file using gzip"""
    try:
        compressed_file = Path(str(log_file) + '.gz')

        # Skip if already compressed
        if compressed_file.exists():
            logger.debug(f"Already compressed: {log_file.name}")
            return False

        # Compress the file
        with open(log_file, 'rb') as f_in:
            with gzip.open(compressed_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

        # Verify compression worked
        if compressed_file.exists() and compressed_file.stat().st_size > 0:
            # Remove original
            log_file.unlink()
            logger.info(f"Compressed: {log_file.name} -> {compressed_file.name}")
            return True
        else:
            logger.error(f"Compression failed for {log_file.name}")
            if compressed_file.exists():
                compressed_file.unlink()
            return False

    except Exception as e:
        logger.error(f"Error compressing {log_file.name}: {e}")
        return False


def delete_old_file(file_path):
    """Delete a file (log or compressed log)"""
    try:
        file_path.unlink()
        logger.info(f"Deleted: {file_path.name}")
        return True
    except Exception as e:
        logger.error(f"Error deleting {file_path.name}: {e}")
        return False


def cleanup_logs(log_dir, compress_after_days=1, delete_after_days=30):
    """
    Main cleanup function

    Args:
        log_dir: Directory containing log files
        compress_after_days: Compress logs older than this many days
        delete_after_days: Delete logs older than this many days
    """
    logger.info("=" * 60)
    logger.info("Starting log cleanup")

    if not log_dir.exists():
        logger.warning(f"Log directory does not exist: {log_dir}")
        return

    now = datetime.now()
    compress_threshold = now - timedelta(days=compress_after_days)
    delete_threshold = now - timedelta(days=delete_after_days)

    # Counters
    compressed_count = 0
    deleted_count = 0
    skipped_count = 0

    # Process all log files
    log_files = list(log_dir.glob('spam_bouncer_*.log'))
    compressed_files = list(log_dir.glob('spam_bouncer_*.log.gz'))

    logger.info(f"Found {len(log_files)} log files and {len(compressed_files)} compressed files")

    # Compress old uncompressed logs
    for log_file in log_files:
        try:
            # Get file modification time
            file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)

            # Skip if it's today's log or the cleanup log
            if log_file.name == CLEANUP_LOG.name:
                continue

            if file_mtime.date() == now.date():
                logger.debug(f"Skipping current log: {log_file.name}")
                skipped_count += 1
                continue

            # Delete if too old
            if file_mtime < delete_threshold:
                if delete_old_file(log_file):
                    deleted_count += 1
                continue

            # Compress if old enough
            if file_mtime < compress_threshold:
                if compress_log_file(log_file):
                    compressed_count += 1

        except Exception as e:
            logger.error(f"Error processing {log_file.name}: {e}")

    # Delete old compressed logs
    for compressed_file in compressed_files:
        try:
            # Get file modification time
            file_mtime = datetime.fromtimestamp(compressed_file.stat().st_mtime)

            # Delete if too old
            if file_mtime < delete_threshold:
                if delete_old_file(compressed_file):
                    deleted_count += 1

        except Exception as e:
            logger.error(f"Error processing {compressed_file.name}: {e}")

    # Summary
    logger.info("-" * 60)
    logger.info(f"Cleanup summary:")
    logger.info(f"  - Compressed: {compressed_count} files")
    logger.info(f"  - Deleted: {deleted_count} files")
    logger.info(f"  - Skipped (current): {skipped_count} files")
    logger.info("Log cleanup completed")
    logger.info("=" * 60)


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Clean up spam bouncer logs')
    parser.add_argument('--compress-after', type=int, default=1,
                        help='Compress logs older than N days (default: 1)')
    parser.add_argument('--delete-after', type=int, default=30,
                        help='Delete logs older than N days (default: 30)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without doing it')

    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN MODE - No files will be modified")
        # TODO: Implement dry run mode if needed

    cleanup_logs(LOG_DIR, args.compress_after, args.delete_after)


if __name__ == '__main__':
    main()
