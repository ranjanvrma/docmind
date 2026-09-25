"""Generate the small demo PDFs used by the sample evaluation dataset.

The documents are fictional and were written for this project. They exist
only so the evaluation pipeline can be run end-to-end out of the box; results
on them do not measure real-world performance.

    python evaluation/make_sample_docs.py
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

OUTPUT_DIR = Path(__file__).resolve().parent / "sample_docs"

DOCUMENTS: dict[str, list[str]] = {
    "remote_work_policy.pdf": [
        """Northwind Analytics - Remote Work Policy (Version 2.1)

1. Purpose and Scope
This policy explains how employees of Northwind Analytics may work from locations other than a company office. It applies to all full-time and part-time employees. Contractors are covered by their individual service agreements and are not covered by this policy.

2. Eligibility
Employees become eligible for remote work after completing a probation period of three months. Eligibility also requires a satisfactory rating in the most recent performance review. Roles that require physical presence, such as laboratory technicians and facilities staff, are not eligible for regular remote work.

3. Requesting Remote Work
Employees submit a remote work request to their line manager through the HR portal. Managers must respond within ten working days. Approved arrangements are reviewed every six months. Employees may work remotely for up to three days per week; fully remote arrangements require approval from a department director.""",
        """4. Equipment and Expenses
The company provides a laptop, a monitor and a headset to every approved remote employee. Employees may claim a one-time home office allowance of 300 euros for furniture such as a desk or chair. Claims must be submitted with receipts within sixty days of purchase.

Internet costs are reimbursed up to 40 euros per month. Electricity and heating costs are not reimbursed. Company equipment remains the property of Northwind Analytics and must be returned within fourteen days when employment ends.

5. Working Hours and Availability
Remote employees must be reachable during the core hours of 10:00 to 15:00 local office time. Meetings should be scheduled within core hours whenever possible. Employees record their working time in the same timesheet system used in the office.""",
        """6. Information Security
Remote employees must connect to company systems only through the corporate VPN. Public Wi-Fi networks may be used only when the VPN is active. Confidential documents must not be printed at home unless a lockable storage cabinet is available.

Laptops must use full-disk encryption and lock automatically after five minutes of inactivity. Lost or stolen devices must be reported to the IT security team within 24 hours.

7. Termination of Arrangements
Either the employee or the manager may end a remote work arrangement with thirty days of written notice. The company may end an arrangement immediately in cases of a serious security breach. Questions about this policy should be directed to the HR department.""",
    ],
    "solar_microgrid_report.pdf": [
        """Riverbend Community Solar Microgrid - Annual Performance Report 2024

Executive Summary
The Riverbend microgrid supplies electricity to 212 households and a primary school. In 2024 the system generated 1,480 megawatt-hours of electricity, which is 6 percent more than in 2023. The increase is mainly explained by the addition of 120 kilowatts of new panels on the school roof in March.

Battery storage allowed the community to cover 71 percent of its evening demand without drawing power from the regional grid. The average household electricity bill fell by 18 percent compared with the year before the microgrid was installed.

The main challenge of the year was an inverter failure in July that reduced output for eleven days.""",
        """Technical Performance
The solar array has a total installed capacity of 1.1 megawatts. The average capacity factor over the year was 15.4 percent. Output peaked in June and was lowest in December, when generation was about one quarter of the June value.

The lithium iron phosphate battery bank has a usable capacity of 2.4 megawatt-hours. Round-trip battery efficiency was measured at 89 percent. The battery management system recorded no thermal incidents during the year.

In July, a failed cooling fan caused one of the four central inverters to shut down. The inverter was replaced after eleven days, during which total output was reduced by roughly a quarter. The supplier covered the replacement under warranty.""",
        """Finances and Recommendations
Operating costs for 2024 were 96,000 euros, of which maintenance contracts accounted for 58 percent. Revenue from selling surplus electricity to the regional grid was 41,000 euros.

Recommendations for 2025:
- Keep a spare inverter cooling fan and one spare inverter on site to shorten repair times.
- Expand battery capacity by 0.8 megawatt-hours to raise evening self-sufficiency above 80 percent.
- Introduce a time-of-use tariff that encourages households to run appliances around midday.
- Commission an independent audit of panel degradation, which the operator estimates at 0.5 percent per year.""",
    ],
    "ml_lecture_notes.pdf": [
        """Machine Learning Fundamentals - Lecture Notes (Week 3)

Gradient Descent
Gradient descent minimises a loss function by repeatedly moving the parameters in the direction of the negative gradient. The update rule is: new weights = old weights minus the learning rate times the gradient of the loss.

The learning rate controls the step size. If it is too large the loss can oscillate or diverge; if it is too small training is very slow. Stochastic gradient descent estimates the gradient from a single example or a small mini-batch instead of the full dataset, which makes each step cheaper but noisier.

Momentum keeps a running average of past gradients, which helps the optimiser move faster along consistent directions and dampens oscillations.""",
        """Overfitting and Regularisation
A model overfits when it learns noise in the training data and performs much worse on unseen data. Typical signs are a training loss that keeps falling while the validation loss starts to rise.

Remedies:
- Collect more training data.
- L2 regularisation (weight decay) adds the sum of squared weights to the loss, which discourages large weights.
- L1 regularisation adds the sum of absolute weights and tends to produce sparse models where many weights are exactly zero.
- Dropout randomly disables a fraction of neurons during training so the network cannot rely on any single unit.
- Early stopping ends training when the validation loss stops improving.""",
        """Evaluating Classifiers
Accuracy is the fraction of correct predictions. It can be misleading on imbalanced datasets: if 95 percent of emails are not spam, a model that never predicts spam is 95 percent accurate.

Precision is the fraction of predicted positives that are actually positive: TP / (TP + FP). Recall is the fraction of actual positives that the model finds: TP / (TP + FN). The F1 score is the harmonic mean of precision and recall.

K-fold cross-validation splits the data into k parts, trains on k-1 parts and tests on the remaining part, repeating k times. The average score is a more reliable estimate than a single train/test split, especially for small datasets.""",
    ],
}


def build_pdf(pages: list[str], path: Path) -> None:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()  # A4 by default
        overflow = page.insert_textbox(pymupdf.Rect(50, 50, 545, 800), text, fontsize=10, fontname="helv")
        if overflow < 0:
            raise ValueError(f"Text does not fit on one page in {path.name}")
    # A fixed metadata dict + no timestamps keeps the output byte-stable, so
    # document IDs (content hashes) are reproducible across runs.
    doc.set_metadata({"title": path.stem, "creationDate": "", "modDate": "", "producer": "DocMind", "creator": "DocMind"})
    doc.save(path, garbage=4, deflate=True, no_new_id=True)
    doc.close()


def main() -> list[Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, pages in DOCUMENTS.items():
        path = OUTPUT_DIR / name
        build_pdf(pages, path)
        paths.append(path)
        print(f"wrote {path.relative_to(OUTPUT_DIR.parent.parent)} ({len(pages)} pages)")
    return paths


if __name__ == "__main__":
    main()
