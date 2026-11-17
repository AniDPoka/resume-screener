"""Writes the sample job description and 8 synthetic resumes into data/.

Everyone here is made up. Emails use example.com (a domain reserved for examples), phone numbers
use the UK range kept for TV and film (07700 900xxx), and the streets are invented.

The content is fixed (no randomness), so running this again always gives the same files.
Run with:  .venv/bin/python data/make_resumes.py
"""

import struct
import zlib
from io import BytesIO
from pathlib import Path

from fpdf import FPDF

DATA = Path(__file__).parent
RESUMES = DATA / "resumes"

JOB = """\
Job title: HR Data Analyst
Team: People Analytics, Northbridge Logistics (fictional company)

About the role
You will turn HR data into clear reports that help managers make fair decisions about their teams.

Must-have:
- At least 2 years of experience working with HR or people data
- Advanced Excel (pivot tables, lookups)
- Building regular reports or dashboards for managers
- Working knowledge of data protection (GDPR) when handling employee data

Nice-to-have:
- SQL
- Power BI or Tableau
- Python
- Experience with an HR system such as Workday or SAP SuccessFactors
- CIPD qualification
"""

# Each resume: (file name, text). The layout is the same for all of them (Name, Contact,
# Address, Summary, Experience, Education, Skills) so later phases can find each part by rule.
RESUME_TEXTS = {
    # Strong match: every must-have and most nice-to-haves.
    "01_priya_raman.txt": """\
Name: Priya Raman
Email: priya.raman@example.com
Phone: 07700 900101
Address: 14 Larkfield Road, Brindlemouth, BR4 7QT

Summary
Priya is an HR data analyst with 5 years of experience in people analytics. She builds monthly
headcount and attrition dashboards in Power BI for senior managers.

Experience
HR Data Analyst, Calderwood Retail (2021 - present)
- Built monthly attrition and absence dashboards in Power BI used by 40 managers
- Wrote SQL queries against the Workday reporting database
- Ran the yearly GDPR data audit for employee records
HR Assistant, Fenmoor Council (2019 - 2021)
- Kept the headcount report in Excel using pivot tables and XLOOKUP

Education
BSc Business Management, University of Ashcombe, graduated 2019
CIPD Level 5 Associate Diploma in People Management, 2022

Skills
Advanced Excel (pivot tables, XLOOKUP), SQL, Power BI, Workday, GDPR
""",
    # Strong match from a different angle: more technical, fewer HR systems.
    "02_daniel_okafor.txt": """\
Name: Daniel Okafor
Email: daniel.okafor@example.com
Phone: 07700 900102
Address: 3 Quarry Lane, Holtsby, HB2 9LP

Summary
Daniel is a people analytics specialist with 4 years of experience. He automates HR reporting
with Python and SQL and presents findings to leadership.

Experience
People Analytics Specialist, Greystone Health (2022 - present)
- Automated the weekly recruitment report with Python, saving 6 hours a week
- Built Tableau dashboards on turnover and time-to-hire for hospital managers
- Wrote data-handling guidance for the team in line with GDPR
Reporting Analyst, Greystone Health (2020 - 2022)
- Maintained Excel models with pivot tables and VLOOKUP for HR and finance

Education
MSc Data Science, Northfield Institute, graduated 2020

Skills
Python, SQL, Tableau, Advanced Excel, SAP SuccessFactors, GDPR
""",
    # Medium: solid HR and Excel, reporting, but no SQL or BI tools.
    "03_sophie_clarke.txt": """\
Name: Sophie Clarke
Email: sophie.clarke@example.com
Phone: 07700 900103
Address: 27 Willow Crescent, Marston Vale, MV1 3RD

Summary
Sophie is an HR advisor with 3 years of experience. She prepares the monthly people report
for the leadership team and supports managers with absence cases.

Experience
HR Advisor, Brookhaven Hotels (2022 - present)
- Prepared the monthly people report in Excel for the leadership team
- Used pivot tables to track sickness absence by site
- Answered subject access requests under GDPR
HR Administrator, Brookhaven Hotels (2021 - 2022)
- Updated employee records in the HR system

Education
BA Psychology, University of Ashcombe, graduated 2021

Skills
Excel (pivot tables), employee relations, absence management, GDPR
""",
    # Medium: strong data skills, but no HR data. Saved as a PDF with a photo-style image.
    "04_mohammed_hassan.pdf": """\
Name: Mohammed Hassan
Email: mohammed.hassan@example.com
Phone: 07700 900104
Address: 9 Ferry Street, Kelton Bridge, KB5 2NW

Summary
Mohammed is a finance data analyst with 4 years of experience building dashboards and
automating reports. He is looking to move into people analytics.

Experience
Finance Data Analyst, Orchard Mutual (2021 - present)
- Built Power BI dashboards on monthly spending for budget holders
- Wrote SQL and Python scripts to automate the month-end report
- Used Excel pivot tables and INDEX MATCH for forecasting models

Education
BSc Economics, Northfield Institute, graduated 2021

Skills
SQL, Python, Power BI, Advanced Excel, financial reporting
""",
    # Medium, with strong age signals (graduated 1992, 30 years). Useful for the bias check later.
    "05_margaret_ellis.txt": """\
Name: Margaret Ellis
Email: margaret.ellis@example.com
Phone: 07700 900105
Address: 51 Orchard Way, Pennick, PN8 4AF

Summary
Margaret is an HR manager with over 30 years of experience. She has produced the quarterly
workforce report for the board for the last 12 years.

Experience
HR Manager, Ridgeway Engineering (2008 - present)
- Produced the quarterly workforce report for the board using Excel pivot tables
- Led the company's move to SAP SuccessFactors in 2019
- Wrote the employee data retention policy when GDPR came into force
HR Officer, Ridgeway Engineering (1994 - 2008)
- Kept staff records and salary data in Excel and Access

Education
BA History, University of Ashcombe, graduated 1992
CIPD Chartered Member

Skills
Excel (pivot tables, VLOOKUP), SAP SuccessFactors, GDPR, workforce planning
""",
    # Weak: retail supervisor, little data work.
    "06_tom_becker.txt": """\
Name: Tom Becker
Email: tom.becker@example.com
Phone: 07700 900106
Address: 8 Market Row, Dunlow, DN3 6HS

Summary
Tom is a retail store supervisor with 6 years of experience leading shift teams.

Experience
Store Supervisor, Penny Lane Foods (2019 - present)
- Wrote weekly staff rotas for a team of 25
- Tracked lateness in a shared spreadsheet
- Trained new starters on till and safety procedures

Education
BTEC Level 3 Business, Dunlow College, completed 2018

Skills
Team leadership, rota planning, basic Excel, customer service
""",
    # Weak, with strong youth signals (recent graduate, internship).
    "07_aisha_bello.txt": """\
Name: Aisha Bello
Email: aisha.bello@example.com
Phone: 07700 900107
Address: Flat 2, 40 College Road, Brindlemouth, BR1 2EX

Summary
Aisha is a recent psychology graduate looking for her first HR analytics role.

Experience
HR Intern, Calderwood Retail (Summer 2025)
- Cleaned survey data in Excel for the engagement report
- Made charts for the intern project presentation

Education
BSc Psychology, University of Ashcombe, graduated 2025
- Dissertation used SPSS to analyse student wellbeing survey data

Skills
Excel, SPSS, survey design, presentations
""",
    # Vague on purpose: big claims, little concrete evidence. Saved as a PDF (no image).
    # The AI is more likely to stretch the evidence or score it differently each time.
    "08_liam_murphy.pdf": """\
Name: Liam Murphy
Email: liam.murphy@example.com
Phone: 07700 900108
Address: 22 Harbour View, Saltmere, SM7 1JD

Summary
Liam is a data-driven people leader passionate about insights, transformation and
helping organisations unlock the value of their workforce.

Experience
People Partner, Bright Horizon Logistics (2022 - present)
- Championed a culture of insight across the business
- Partnered with stakeholders on people metrics
- Involved in reporting and analytics initiatives
Talent Coordinator, Bright Horizon Logistics (2020 - 2022)
- Supported hiring managers throughout the recruitment process

Education
BA Business and Marketing, Saltmere University, graduated 2020

Skills
Stakeholder management, insights, analytics, Microsoft Office
""",
}


def tiny_png():
    """A small grey square as PNG bytes, standing in for a photo. Built by hand so no picture
    library is needed."""
    width = height = 40
    rows = b"".join(b"\x00" + b"\xa0\xa0\xa0" * width for _ in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit colour, no transparency
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def write_pdf(path, text, with_image):
    """Saves the resume text as a one-page PDF, optionally with a photo-style image in the corner."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    if with_image:
        pdf.image(BytesIO(tiny_png()), x=170, y=10, w=25)
    for line in text.splitlines():
        # Width 150 leaves room for the image and makes long lines wrap, as real PDFs do.
        pdf.multi_cell(150, 6, line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))


def main():
    RESUMES.mkdir(exist_ok=True)
    (DATA / "job_description.txt").write_text(JOB, encoding="utf-8")
    for name, text in RESUME_TEXTS.items():
        path = RESUMES / name
        if name.endswith(".pdf"):
            write_pdf(path, text, with_image=(name == "04_mohammed_hassan.pdf"))
        else:
            path.write_text(text, encoding="utf-8")
    print(f"Wrote the job description and {len(RESUME_TEXTS)} resumes to {DATA}")


if __name__ == "__main__":
    main()
