"""Compatibility entry point; shared implementation remains in extra_functions."""
from extra_functions.build_database import build_database, main, merge_dataset

__all__ = ["build_database", "main", "merge_dataset"]

if __name__ == "__main__":
    main()
