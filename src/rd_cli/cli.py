import argparse
import sys
from dotenv import load_dotenv
from rd_cli import api

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rd",
        description="Raindrop.io CLI Client"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    list_parser = subparsers.add_parser("list", help="List raindrops")
    list_parser.add_argument("-c", "--collection", type=int, default=0, help="Collection ID (0 for Unsorted, default: 0)")
    list_parser.add_argument("-s", "--search", type=str, default="", help="Search query")

    # add
    add_parser = subparsers.add_parser("add", help="Add a new raindrop")
    add_parser.add_argument("url", help="URL to bookmark")
    add_parser.add_argument("-t", "--title", help="Custom title")
    add_parser.add_argument("-c", "--collection", type=int, default=0, help="Collection ID")
    add_parser.add_argument("--tags", nargs="*", help="Tags for the bookmark")

    # edit
    edit_parser = subparsers.add_parser("edit", help="Edit a raindrop")
    edit_parser.add_argument("id", type=int, help="Raindrop ID")
    edit_parser.add_argument("-t", "--title", help="New title")
    edit_parser.add_argument("--tags", nargs="*", help="New tags")

    # rm
    rm_parser = subparsers.add_parser("rm", help="Remove a raindrop")
    rm_parser.add_argument("id", type=int, help="Raindrop ID")

    return parser

def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    if argv is None:
        argv = sys.argv[1:]
    
    parser = build_parser()
    if not argv:
        parser.print_help()
        return 0

    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            items = api.get_raindrops(collection_id=args.collection, search=args.search)
            if not items:
                print("No raindrops found.")
            for item in items:
                print(f"[{item['_id']}] {item.get('title', 'No Title')} - {item['link']}")

        elif args.command == "add":
            item = api.add_raindrop(args.url, title=args.title, collection_id=args.collection, tags=args.tags)
            print(f"Added raindrop: [{item.get('_id')}] {item.get('title')} - {item.get('link')}")

        elif args.command == "edit":
            item = api.edit_raindrop(args.id, title=args.title, tags=args.tags)
            print(f"Edited raindrop: [{item.get('_id')}] {item.get('title')}")

        elif args.command == "rm":
            success = api.delete_raindrop(args.id)
            if success:
                print(f"Successfully deleted raindrop {args.id}")
            else:
                print(f"Failed to delete raindrop {args.id}")
                return 1

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
