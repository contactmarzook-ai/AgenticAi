"""Entry point for the scheduler process: python -m app.scheduler"""

from .services.scheduler import main

if __name__ == "__main__":
    main()
