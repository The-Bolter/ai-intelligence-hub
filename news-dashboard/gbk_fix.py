import pathlib, py_compile, os

d = pathlib.Path(__file__).parent
fp = d / "app.py"
code = fp.read_text("utf-8")

code = code.replace(
    'return render_template("index.html")',
    'html = render_template("index.html")\nresp = make_response(html)\nresp.headers["Content-Type"] = "text/html; charset=gbk"\nreturn resp'
)
code = code.replace(
    "from flask import Flask, jsonify, render_template, request, abort",
    "from flask import Flask, jsonify, make_response, render_template, request, abort"
)

fp.write_text(code, "utf-8")
py_compile.compile(str(fp), doraise=True)
print("GBK Content-Type set in index()")
os.remove(str(d / "gbk_fix.py"))
print("Cleaned")
