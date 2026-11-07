"""
scripts/generate_pdf.py — Generate high quality project-writeup.pdf using fpdf2.
"""

from fpdf import FPDF
import os

class WriteupPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, "ResourceLens -- Industrial Energy and Water Loss Investigation | Problem 22", align="R")
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

def main():
    pdf = WriteupPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(20, 35, 60)
    pdf.cell(0, 10, "ResourceLens: Industrial Energy & Water Loss", ln=True)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(37, 99, 235)
    pdf.cell(0, 7, "Autonomous Investigation for Small and Medium Factories", ln=True)

    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, "Team: ResourceLens Engineering Team | Capstone Project 22 | December 2026", ln=True)
    pdf.ln(3)

    # Decorative Line
    pdf.set_draw_color(37, 99, 235)
    pdf.set_line_width(0.6)
    pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
    pdf.ln(5)

    def heading(text):
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(30, 64, 175)
        pdf.cell(0, 7, text, ln=True)
        pdf.ln(1)

    def body_p(text):
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(0, 5, text)
        pdf.ln(2)

    def bullet(bold_prefix, text):
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(20, 20, 20)
        pdf.cell(5, 5, "- ")
        pdf.cell(pdf.get_string_width(bold_prefix + " "), 5, bold_prefix + " ")
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(50, 50, 50)
        pdf.multi_cell(0, 5, text)
        pdf.ln(1.5)

    heading("1. Executive Summary & Problem Formulation")
    body_p(
        "Small and medium industrial manufacturing plants frequently encounter sudden 15% to 35% surges in electricity and "
        "water bills. While smart sub-meters capture continuous consumption, facilities lack the engineering bandwidth to "
        "correlate electrical spikes or water imbalances with physical reality: maintenance sheets, pending repair orders, "
        "shift transitions, or machine operating habits."
    )
    body_p(
        "ResourceLens solves this problem by acting as an autonomous industrial investigator. It ingests 15-minute electrical telemetry "
        "or daily water balance records, photographs of handwritten inspection logs and equipment nameplates, and operator voice notes "
        "recorded on the shop floor. It correlates meter anomalies with human observations to diagnose root causes and recommend "
        "actionable, human-reviewed maintenance tasks."
    )

    heading("2. Architecture & Design Principles")
    body_p("ResourceLens is governed by three strict architectural mandates:")
    bullet("1. Separation of Determinism and Heuristics:", 
           "The AI never performs arithmetic. Baseline calculation (same-shift, same-weekday rolling 4-week mean mu and standard deviation sigma), "
           "anomaly thresholding (max(T%, 2sigma)), volumetric water balance (Intake - Process - Discharge), and financial tariffs are executed purely in Python.")
    bullet("2. Multimodal Evidence Grounding:", 
           "Nexus Vision digitizes inspection logs with per-field confidence scoring; Nexus STT transcribes operator audio into timestamped segments. "
           "Nexus LLM links anomalies to cited evidence (VN-xx, IMG-xx). Every citation is verified via substring matching in application code before presentation. "
           "If evidence is lacking, the system strictly reports 'cause unknown'.")
    bullet("3. Mandatory Human-in-the-Loop Review:", 
           "The AI never controls physical equipment. Recommended work orders remain in a pending state until the plant manager approves, edits, "
           "or rejects them. The secondary output -- a synthesized audio briefing for the incoming shift team generated via Nexus TTS -- is produced exclusively "
           "from manager-approved actions.")

    heading("3. Comprehensive Feature Scope (Energy + Water Tracks)")
    bullet("Energy Track:", "Ingests 15-minute interval kWh readings, maps to 3 daily shifts (Day, Evening, Night), flags compressor overruns, "
           "weekend idle runs, and equipment degradation drift.")
    bullet("Water Track:", "Solves daily water balances, detects cooling tower leaks (+18 kL/day), and flags impossible metering discrepancies (Discharge > Intake).")
    bullet("Time-of-Day (ToD) Tariff Engine:", "Applies differential peak (Rs 9.0/kWh) and off-peak (Rs 7.5/kWh) rates for energy, and Rs 45.0/kL for water.")
    bullet("Post-Fix Verification Engine:", "Ingests post-repair meter files to measure actual percentage drop against baseline and compute verified cost savings.")
    bullet("Rich Analytics UI:", "Interactive Recharts time-series bands with anomaly highlights and water balance bar graphs.")

    heading("4. Verification, Testing & Robustness")
    bullet("Unit & Hand-Calculation Verification:", 
           "52 comprehensive unit tests (backend/tests/) confirm 100% mathematical validity of energy baselines, water equations, "
           "tariff calculations, validation logic, review state machine, and post-fix verification against manual hand-calculations.")
    bullet("Evaluation Benchmark:", 
           "15 test cases spanning normal runs, missing evidence, conflicting reports, degraded captures, and adversarial prompt injections (Categories A-F) "
           "achieving 15/15 PASS (100.0%).")
    bullet("Engineering Transparency:", 
           "5 documented development mistakes logged in AI_USAGE.md detailing root cause discovery, code fixes, and regression prevention.")

    output_path = "project-writeup.pdf"
    pdf.output(output_path)
    print(f"Generated {output_path} ({os.path.getsize(output_path)} bytes)")

if __name__ == "__main__":
    main()
