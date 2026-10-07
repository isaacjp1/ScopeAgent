"""Print what the agent sees on some pages of the practice clinic.

    docker run --rm zeren-agent python3 -m agent.inspect_pages "/patients?lastName=Jones" "/patients/<id>"
"""
import asyncio
import sys

from .site import Site


async def main(paths):
    site = Site()
    await site.start()
    for p in paths:
        data = await site.read(p)
        print(site.render(data, max_chars=20000))
        print()
    await site.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["/"]))
