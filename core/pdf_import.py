"""Read a college curriculum/syllabus PDF into a course table and syllabus units.

Works on text-based PDFs (not scanned images). It looks for:
- semester headings ("Semester III", "SEM 3", "Third Semester", "III Semester"),
- course rows: a course code (e.g. 23CSE101, CS301, 21CS42, MA-101) followed by a
  title, optional L-T-P hours and a credit value,
- elective slots inside a semester ("Professional Elective II ... 3"),
- each course's syllabus: "Unit 1 / Module 2 ..." blocks after the course code,
  or one "Syllabus" paragraph, plus its textbooks.

The result is meant to be reviewed and corrected by a person before saving.
"""

from __future__ import annotations

import re

import pandas as pd

CODE = re.compile(r"^(?=[A-Z0-9-]{5,12}$)(?=.*[A-Z])(?=(?:.*\d){2})[A-Z0-9]+(?:-[A-Z0-9]+)?$")
LTP_DASH = re.compile(r"^\d{1,2}-\d{1,2}-\d{1,2}$")
NUM = re.compile(r"^\d{1,2}(?:\.\d)?$")
PASSFAIL = re.compile(r"^\(?P/F\)?$|^\[\d\]$", re.I)
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}
ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
           "ninth": 9, "tenth": 10}
SEM_PATTERNS = [
    re.compile(r"\b(?:semester|sem)\s*[-:.]?\s*(X|IX|VIII|VII|VI|IV|V|III|II|I|\d{1,2})\b", re.I),
    re.compile(r"\b(X|IX|VIII|VII|VI|IV|V|III|II|I|\d{1,2})(?:st|nd|rd|th)?\s+(?:semester|sem)\b", re.I),
    re.compile(r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+semester\b", re.I),
]
UNIT = re.compile(r"^\s*(?:UNIT|Unit|Module|MODULE|Chapter|CHAPTER)[\s\-:]*(?:[IVX]+|\d+)\b[\s:.\-]*", re.M)
END = re.compile(r"^\s*(?:Text\s*Books?|Textbooks?|Text\s*Book\(s\)|Textbook\(s\)|References?|Reference\s*Books?|"
                 r"Lab\s+(?:Syllabus|Practice|Exercises|Experiments)|List of|Laboratory|Lab Exercises|Evaluation|"
                 r"Course Outcomes|Practicals?|Experiments|Suggested Readings?)", re.M | re.I)
TEXTBOOKS = re.compile(r"^\s*(?:Text\s*Books?|Textbooks?|Text\s*Book\(s\)|Textbook\(s\)|Reference\s*/\s*Text\s*Books?|"
                       r"Text\s*Books?\s*/\s*Reference\s*Books?)[^\n]*$(.{20,900}?)(?=^\s*(?:References?|Reference Books?|"
                       r"Evaluation|Course Outcomes|Lab)\b|\Z)", re.S | re.M | re.I)


def _semester_number(text: str) -> int | None:
    for p in SEM_PATTERNS:
        m = p.search(text)
        if m:
            v = m.group(1)
            n = ROMAN.get(v.upper()) or ORDINAL.get(v.lower()) or (int(v) if v.isdigit() else None)
            if n and 1 <= n <= 12:
                return n
    return None


def _lines(page, tol: float = 3):
    words = sorted(page.get_text("words"), key=lambda w: (round(w[1]), w[0]))
    out = []
    for w in words:
        if out and abs(out[-1][0] - w[1]) <= tol:
            out[-1][1].append(w)
        else:
            out.append([w[1], [w]])
    return [(y, sorted(ws, key=lambda w: w[0])) for y, ws in out]


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" .;-:*")


def tidy_unit(text: str) -> str:
    """Drop hour counts and textbook chapter references from a syllabus unit."""
    t = _clean(text)
    t = re.sub(r"\((?:Text\s*Book|TB|Ref)[^)]{0,60}\)", " ", t, flags=re.I)
    t = re.sub(r"\b\d{1,2}\s*(?:Hours|Hrs|Hr|L)\b\.?", " ", t)
    t = re.sub(r"^(?:[IVX]+|\d+)\s*[:.\-]\s*", "", t.strip())
    return _clean(t)


def guess_program(doc) -> str:
    """A program name from the first pages, e.g. 'B.Tech - Computer Science and Engineering'."""
    for page in list(doc)[:3]:
        for line in page.get_text().splitlines():
            line = _clean(line)
            if re.search(r"\b(B\.?\s?Tech|B\.?\s?E\b|Bachelor|M\.?\s?Tech|B\.?Sc|BCA|MCA)", line, re.I) and 6 <= len(line) <= 90:
                return line
    return ""


def extract_courses(doc, branch: str) -> tuple[pd.DataFrame, list[str]]:
    """Course rows grouped by semester. Returns (table, notes)."""
    rows, notes, seen = [], [], set()
    semester, found_heading = None, False
    for pno, page in enumerate(doc, 1):
        last = None
        for y, ws in _lines(page):
            texts = [w[4] for w in ws]
            line = " ".join(texts)
            codes = [w for w in ws if CODE.match(w[4].strip(".,*"))]
            if not codes and len(texts) <= 6:
                n = _semester_number(line)
                if n:
                    semester, found_heading, last = n, True, None
                    continue
                if re.search(r"elective", line, re.I) and not any(NUM.match(t) for t in texts):
                    semester, last = None, None  # an elective list, not a semester table
                    continue
            if codes:
                c = codes[0]
                code = c[4].strip(".,*")
                after = [w for w in ws if w[0] > c[0]]
                nums = [w for w in after if NUM.match(w[4]) or LTP_DASH.match(w[4]) or PASSFAIL.match(w[4])]
                title_words = [w[4] for w in after if (not nums or w[0] < nums[0][0]) and not CODE.match(w[4])]
                title = _clean(" ".join(title_words))
                if not title or code in seen or not nums:
                    last = None
                    continue
                if semester is None and found_heading:
                    last = None
                    continue
                dash = [w[4] for w in nums if LTP_DASH.match(w[4])]
                singles = [w[4] for w in nums if NUM.match(w[4])]
                ltp = dash[0] if dash else ("-".join(singles[:3]) if len(singles) >= 4 else "")
                pf = [w[4].strip("()") for w in nums if PASSFAIL.match(w[4])]
                credits = pf[-1] if pf and (not singles or nums[-1][4].strip("()") == pf[-1]) else (singles[-1] if singles else "")
                cat = next((w[4] for w in ws if w[0] < c[0] and w[4].isupper() and w[4].isalpha() and len(w[4]) <= 6), "")
                seen.add(code)
                last = dict(branch=branch, semester=semester or 1, code=code, title=title, category=cat, ltp=ltp,
                            credits=credits, _y=y, _x=c[2], _page=pno)
                rows.append(last)
            elif semester and re.search(r"elective", line, re.I) and texts and NUM.match(texts[-1]):
                words = [t for t in texts if not re.match(r"^[\d*\-]+$", t)]
                while words and words[0].isupper() and words[0].isalpha() and len(words[0]) <= 5 and len(words) > 1:
                    words.pop(0)  # a leading category such as ENGG or ELE
                title = _clean(" ".join(words))
                rows.append(dict(branch=branch, semester=semester, code="", title=title, category="", ltp="",
                                 credits=texts[-1], _y=y, _x=0, _page=pno))
                last = None
            elif last and y - last["_y"] < 22 and last["_page"] == pno:
                extra = [w[4] for w in ws if w[0] >= last["_x"] - 2 and not NUM.match(w[4]) and not LTP_DASH.match(w[4])
                         and not re.match(r"^\d+:\d+$", w[4])]
                if extra and len(extra) <= 8:
                    last["title"] = _clean(last["title"] + " " + " ".join(extra))
                last = None
    if not found_heading and rows:
        notes.append("No semester headings were found, so every course was put in semester 1. Fix the Semester column.")
    df = pd.DataFrame(rows, columns=["branch", "semester", "code", "title", "category", "ltp", "credits", "_y", "_x", "_page"])
    return df.drop(columns=["_y", "_x", "_page"]), notes


def extract_syllabus(doc, codes: list[str]) -> dict:
    """{code: {"units": [...], "textbooks": [...]}} for the courses whose syllabus is found."""
    text = "\n".join(p.get_text() for p in doc)
    text = text.replace("–", "-").replace("—", "-").replace("", "").replace("●", "")
    positions = {c: [m.start() for m in re.finditer(re.escape(c), text)] for c in codes}
    all_pos = sorted(p for c in codes for p in positions[c])
    out = {}
    for code in codes:
        for start in positions[code]:
            nxt = next((p for p in all_pos if p > start + 20 and text[p:p + 12].split()[0] != code), len(text))
            block = text[start:nxt]
            units = []
            us = list(UNIT.finditer(block))
            for j, u in enumerate(us):
                seg = block[u.end(): us[j + 1].start() if j + 1 < len(us) else len(block)]
                e = END.search(seg)
                if e:
                    seg = seg[: e.start()]
                seg = tidy_unit(seg)
                if len(seg) > 15:
                    units.append(seg[:900])
            if not units:
                m = re.search(r"^\s*(?:Syllabus|SYLLABUS|Course Content|Contents)\s*$(.{30,2500}?)(?=^\s*(?:Text|Reference|Lab|Evaluation)|\Z)",
                              block, re.S | re.M)
                if m:
                    topics = [_clean(x) for x in re.split(r"\s-\s|,\s|;\s|\.\s", _clean(m.group(1))) if len(_clean(x)) > 3]
                    if len(topics) >= 3:
                        k = -(-len(topics) // 3)
                        units = ["; ".join(topics[n:n + k]) for n in range(0, len(topics), k)]
            if units:
                books = []
                t = TEXTBOOKS.search(block)
                if t:
                    parts = re.split(r"\n\s*(?:\d+\s*[.)]|\[\d+\]|•)\s*", "\n" + t.group(1))
                    books = [_clean(x) for x in parts if len(_clean(x)) > 15][:3]
                out[code] = {"units": units[:8], "textbooks": books}
                break
    return out


def import_pdf(data: bytes, branch: str = "") -> tuple[pd.DataFrame, dict, list[str], str]:
    """Parse one PDF. Returns (course table, syllabus, notes, guessed program name)."""
    import pymupdf  # imported here so the rest of the app works without it

    doc = pymupdf.open(stream=data, filetype="pdf")
    program = guess_program(doc)
    df, notes = extract_courses(doc, branch or program or "Program")
    if df.empty:
        notes.append("No course rows were found. The PDF may be a scanned image or use an unusual table layout.")
        return df, {}, notes, program
    syl = extract_syllabus(doc, [c for c in df["code"] if c])
    theory = [c for c, t in zip(df["code"], df["title"]) if c and not re.search(r"lab|project|internship", t, re.I)]
    notes.append(f"Found {len(df)} rows in {df['semester'].nunique()} semester(s); syllabus units for "
                 f"{sum(c in syl for c in theory)} of {len(theory)} theory courses.")
    return df, syl, notes, program
