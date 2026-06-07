import os
import shutil


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOCS = os.path.join(ROOT, "docs")
STATIC = os.path.join(ROOT, "web", "static")
PUBLIC = os.path.join(ROOT, "web", "public")


def main():
    if os.path.exists(DOCS):
        shutil.rmtree(DOCS)
    os.makedirs(os.path.join(DOCS, "assets"))
    shutil.copyfile(os.path.join(STATIC, "app.js"), os.path.join(DOCS, "assets", "app.js"))
    shutil.copyfile(os.path.join(STATIC, "styles.css"), os.path.join(DOCS, "assets", "styles.css"))
    shutil.copyfile(os.path.join(PUBLIC, "papers.json"), os.path.join(DOCS, "papers.json"))
    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(
            """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Daily Paper Digest</title>
    <link rel="stylesheet" href="./assets/styles.css" />
  </head>
  <body>
    <div id="root"></div>
    <script crossorigin src="https://unpkg.com/react@17/umd/react.production.min.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@17/umd/react-dom.production.min.js"></script>
    <script src="./assets/app.js"></script>
  </body>
</html>
"""
        )
    with open(os.path.join(DOCS, ".nojekyll"), "w", encoding="utf-8"):
        pass
    print("Built static site into %s" % DOCS)


if __name__ == "__main__":
    main()
