import sys

print("Python version:", sys.version)

try:
    import psycopg2
    print("psycopg2 is installed")
except ImportError:
    print("psycopg2 is NOT installed")

try:
    import psycopg
    print("psycopg (v3) is installed")
except ImportError:
    print("psycopg (v3) is NOT installed")

try:
    import asyncpg
    print("asyncpg is installed")
except ImportError:
    print("asyncpg is NOT installed")
