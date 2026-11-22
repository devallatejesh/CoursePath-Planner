"""Hand-picked study resources matched to a subject by its title.

For every subject, across all universities:
- W3Schools tutorials where W3Schools covers the topic,
- GeeksforGeeks tutorials (or a GeeksforGeeks search for other technical subjects),
- Striver's A2Z DSA sheet (takeUforward) for data structures and algorithms,
- a YouTube "full course" search.
All tutorial links were checked to open the right page.
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus

W3 = "https://www.w3schools.com/"
GFG = "https://www.geeksforgeeks.org/"
STRIVER_A2Z = "https://takeuforward.org/strivers-a2z-dsa-course/strivers-a2z-dsa-course-sheet-2"
STRIVER_SDE = "https://takeuforward.org/interviews/strivers-sde-sheet-top-coding-interview-problems"
STRIVER_YT = "https://www.youtube.com/@takeUforward"

# (pattern on the title, [(site, label, url), ...]) - order sets the order links are shown in.
RULES: list[tuple[str, list[tuple[str, str, str]]]] = [
    (r"data structure|algorithm|\bdsa\b",
     [("Striver", "A2Z DSA Sheet", STRIVER_A2Z), ("Striver", "takeUforward videos", STRIVER_YT),
      ("W3Schools", "DSA", W3 + "dsa/"), ("GeeksforGeeks", "DSA", GFG + "dsa/dsa-tutorial-learn-data-structures-and-algorithms/")]),
    (r"design and analysis of algorithms|analysis of algorithms",
     [("Striver", "SDE Sheet", STRIVER_SDE)]),
    (r"graph theory|graph algorithm", [("GeeksforGeeks", "Graph algorithms", GFG + "dsa/graph-data-structure-and-algorithms/")]),
    (r"python|computational thinking|computational problem solving",
     [("W3Schools", "Python", W3 + "python/"), ("GeeksforGeeks", "Python", GFG + "python/python-programming-language-tutorial/")]),
    (r"object oriented|\boop\b",
     [("W3Schools", "Java", W3 + "java/"), ("W3Schools", "Python classes", W3 + "python/python_classes.asp"),
      ("GeeksforGeeks", "Java", GFG + "java/java/")]),
    (r"\bjava\b", [("W3Schools", "Java", W3 + "java/"), ("GeeksforGeeks", "Java", GFG + "java/java/")]),
    (r"c programming|programming in c\b|procedural programming|problem solving & c|\bc\b.*problem solving",
     [("W3Schools", "C", W3 + "c/"), ("GeeksforGeeks", "C", GFG + "c/c-programming-language/")]),
    (r"c\+\+", [("W3Schools", "C++", W3 + "cpp/"), ("GeeksforGeeks", "C++", GFG + "cpp/c-plus-plus/")]),
    (r"database|dbms|\bsql\b|backend",
     [("W3Schools", "SQL", W3 + "sql/"), ("W3Schools", "MySQL", W3 + "mysql/"),
      ("GeeksforGeeks", "DBMS", GFG + "dbms/dbms/"), ("GeeksforGeeks", "SQL", GFG + "sql/sql-tutorial/")]),
    (r"full stack|web tech|web develop|internet technolog|front ?end|\bui\b|user interface|ui engineering",
     [("W3Schools", "HTML", W3 + "html/"), ("W3Schools", "CSS", W3 + "css/"), ("W3Schools", "JavaScript", W3 + "js/"),
      ("W3Schools", "React", W3 + "react/"), ("W3Schools", "Node.js", W3 + "nodejs/"),
      ("GeeksforGeeks", "Web development", GFG + "web-tech/web-technology/")]),
    (r"machine learning|pattern recognition|\bml\b|tiny ?ml",
     [("W3Schools", "Machine Learning", W3 + "python/python_ml_getting_started.asp"),
      ("W3Schools", "NumPy", W3 + "python/numpy/"), ("W3Schools", "Pandas", W3 + "python/pandas/"),
      ("GeeksforGeeks", "Machine Learning", GFG + "machine-learning/machine-learning-tutorial/")]),
    (r"deep learning|neural", [("GeeksforGeeks", "Deep Learning", GFG + "deep-learning/deep-learning-tutorial/")]),
    (r"artificial intelligence|\bai\b|intelligent|agentic",
     [("W3Schools", "AI", W3 + "ai/"), ("GeeksforGeeks", "Artificial Intelligence", GFG + "artificial-intelligence/artificial-intelligence/")]),
    (r"generative|large language|\bllm|language models?|\bgenai\b",
     [("W3Schools", "Generative AI", W3 + "gen_ai/"), ("GeeksforGeeks", "Generative AI", GFG + "artificial-intelligence/generative-ai-tutorial/")]),
    (r"natural language|\bnlp\b",
     [("GeeksforGeeks", "NLP", GFG + "nlp/natural-language-processing-nlp-tutorial/")]),
    (r"computer vision|image processing|perception",
     [("W3Schools", "Matplotlib", W3 + "python/matplotlib_intro.asp"), ("GeeksforGeeks", "Computer Vision", GFG + "computer-vision/computer-vision/")]),
    (r"data science|data analytic|big data|data processing|power bi|data warehouse|data mining|data pipeline|data engineering",
     [("W3Schools", "Data Science", W3 + "datascience/"), ("W3Schools", "Pandas", W3 + "python/pandas/"),
      ("GeeksforGeeks", "Data Science", GFG + "data-science/data-science-for-beginners/")]),
    (r"probab|statistic|random process|random variable",
     [("W3Schools", "Statistics", W3 + "statistics/"), ("GeeksforGeeks", "Statistics", GFG + "maths/statistics/")]),
    (r"discrete math", [("GeeksforGeeks", "Discrete Mathematics", GFG + "engineering-mathematics/discrete-mathematics-tutorial/")]),
    (r"cyber|security|hacking|penetration|forensic",
     [("W3Schools", "Cyber Security", W3 + "cybersecurity/"), ("GeeksforGeeks", "Cyber Security", GFG + "cybersecurity/cyber-security-tutorial/")]),
    (r"crypt", [("GeeksforGeeks", "Cryptography", GFG + "computer-networks/cryptography-tutorial/")]),
    (r"blockchain", [("GeeksforGeeks", "Blockchain", GFG + "software-engineering/blockchain/")]),
    (r"operating system", [("W3Schools", "Bash", W3 + "bash/"), ("GeeksforGeeks", "Operating Systems", GFG + "operating-systems/operating-systems/")]),
    (r"linux|unix|shell", [("W3Schools", "Bash", W3 + "bash/"), ("GeeksforGeeks", "Linux", GFG + "linux-unix/linux-tutorial/")]),
    (r"network", [("GeeksforGeeks", "Computer Networks", GFG + "computer-networks/computer-network-tutorials/")]),
    (r"compiler|system software", [("GeeksforGeeks", "Compiler Design", GFG + "compiler-design/compiler-design-tutorials/")]),
    (r"automata|theory of computation|formal language",
     [("GeeksforGeeks", "Theory of Computation", GFG + "theory-of-computation/theory-of-computation-automata-tutorials/")]),
    (r"software engineering|agile|software testing|adaptive software",
     [("W3Schools", "Git", W3 + "git/"), ("GeeksforGeeks", "Software Engineering", GFG + "software-engineering/software-engineering/")]),
    (r"devops|ci/cd|mlops", [("W3Schools", "Git", W3 + "git/"), ("GeeksforGeeks", "DevOps", GFG + "devops/devops-tutorial/")]),
    (r"(?<!embedded )system design|scalab",[("GeeksforGeeks", "System Design", GFG + "system-design/system-design-tutorial/")]),
    (r"cloud|\baws\b", [("W3Schools", "AWS Cloud", W3 + "aws/"), ("GeeksforGeeks", "Cloud Computing", GFG + "cloud-computing/cloud-computing/")]),
    (r"digital (logic|electronics|design|principles)|logic design",
     [("GeeksforGeeks", "Digital Electronics", GFG + "digital-logic/digital-electronics-logic-design-tutorials/")]),
    (r"computer organi[sz]ation|computer architecture|microprocessor|computer systems and architecture",
     [("GeeksforGeeks", "Computer Organization & Architecture",
       GFG + "computer-organization-architecture/computer-organization-and-architecture-tutorials/")]),
    (r"calculus|linear algebra|differential equation|transform|numerical|engineering mathematics|mathematics",
     [("W3Schools", "NumPy", W3 + "python/numpy/"),
      ("GeeksforGeeks", "Engineering Mathematics", GFG + "engineering-mathematics/engineering-mathematics-tutorials/")]),
    (r"excel|powerpoint|spreadsheet", [("W3Schools", "Excel", W3 + "excel/")]),
    (r"\bgit\b|version control", [("W3Schools", "Git", W3 + "git/"), ("GeeksforGeeks", "Git", GFG + "git/git-tutorial/")]),
]
_COMPILED = [(re.compile(p, re.I), links) for p, links in RULES]

# Subjects where coding tutorials don't help (languages, values, soft skills, activities...).
NON_TECHNICAL = re.compile(
    r"english|communication skills|technical communication|business communication|language skills|foreign language|kannada|values?\b|constitution|ethics|heritage|mastery over mind|"
    r"glimpses|sports|yoga|environment|ecology|disaster|legal|\bipr\b|management|entrepreneur|liberal|design thinking|"
    r"negotiat|influenc|story|resilience|aptitude|verbal|analytical skills|critical thinking|seminar|activity|life skills|"
    r"soft skills|cognitive and technical|knowledge system|sustainab|bharath|learning how to learn|human values|"
    r"internship|project|term paper|elective|minor\b|certification|leadership|innovation",
    re.I)


def youtube_course_url(title: str) -> str:
    q = re.sub(r"\(.*?\)", "", title).strip()
    return "https://www.youtube.com/results?search_query=" + quote_plus(f"{q} full course")


def gfg_search_url(title: str) -> str:
    q = re.sub(r"\(.*?\)|[-–]\s*\d+$|\b[IVX]+$", "", title).strip()
    return GFG + "search/?gq=" + quote_plus(q)


def recommended(title: str) -> list[tuple[str, str, str]]:
    """(site, label, url) links for a subject: Striver/W3Schools/GeeksforGeeks matches, then YouTube."""
    out, seen = [], set()
    for rx, links in _COMPILED:
        if rx.search(title):
            for site, label, url in links:
                if url not in seen:
                    seen.add(url)
                    out.append((site, label, url))
    if not any(site == "GeeksforGeeks" for site, _, _ in out) and not NON_TECHNICAL.search(title):
        out.append(("GeeksforGeeks", "Search this subject", gfg_search_url(title)))
    out.append(("YouTube", "Full course videos", youtube_course_url(title)))
    order = {"Striver": 0, "W3Schools": 1, "GeeksforGeeks": 2, "YouTube": 3}
    return sorted(out, key=lambda x: order.get(x[0], 9))


def is_dsa(title: str) -> bool:
    return bool(_COMPILED[0][0].search(title))
