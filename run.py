#!/usr/bin/env python3
"""Start the MiniBridge table and learning API."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
