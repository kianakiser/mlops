// MS1 Project Proposal — MLOps HS26 (I.BA_MLOPS)
// Build:  typst compile docs/src/proposal.typ docs/proposal.pdf
//
// HARD CONSTRAINTS from the Proposal Guide:
//   * max 2 pages, PDF
//   * exactly these four headings — each is graded as its own criterion
//   * the FTI diagram must be EMBEDDED AS AN IMAGE (not referenced, not ASCII)
//   * upload to ILIAS "MS1 Submission" WITH the repo URL, and commit a copy as docs/proposal.pdf
//
// Everything still red is unfinished. Ship with zero red on the page.

#let TODO(body) = text(fill: rgb("#c2352b"), weight: "semibold")[[#body]]

#set page(
  paper: "a4",
  margin: (x: 1.8cm, y: 1.7cm),
  footer: context [
    #set text(8pt, fill: luma(110))
    #h(1fr) #counter(page).display("1 / 1", both: true)
  ],
)
#set text(font: ("Helvetica Neue", "Helvetica", "Arial"), size: 9.5pt)
#set par(justify: true, leading: 0.62em)
#show heading.where(level: 1): it => block(above: 0.9em, below: 0.55em)[
  #set text(11pt, weight: "bold")
  #it.body
]

// ---------------------------------------------------------------- title block
#block[
  #set text(15pt, weight: "bold")
  Project Proposal — #TODO[project title]
]
#v(-0.3em)
#block[
  #set text(9pt, fill: luma(80))
  Kiana Kiser · MLOps HS26 · I.BA_MLOPS · Repository: #TODO[public GitHub URL]
]
#v(0.25em)
#line(length: 100%, stroke: 0.5pt + luma(180))

= 1 Problem statement

// Guide: what do you predict, and for whom? EXACT horizon. Scope. Success criterion
// WITH A NUMBER AND A BASELINE.
// Strong: "Predict per-station bike availability 60 min ahead, MAE <= 2, beating persistence."
// Weak:   "Analyse bike-sharing data."

#TODO[One sentence: what you predict, the exact horizon, and for whom.]

*Scope.* #TODO[Which entities / assets / region / period.]

*Success criterion.* #TODO[Metric with a number], measured against the baseline
#TODO[name it — e.g. persistence: last observed value carried forward] on an out-of-time
test split.

= 2 Originality & motivation

// Guide: why this problem, and why YOU? Checked against mlops-lab.ch and KTH ID2223?
// One sentence on what makes yours different.
// Crypto direction / air quality / news classification are done repeatedly and score low.

#TODO[Why this problem matters, and your own connection to it — this is the "why you".]

*Checked against prior work.* I reviewed the HSLU project showcase (mlops-lab.ch) and the
KTH ID2223 project lists. #TODO[What is closest, and one sentence on what makes yours different.]

= 3 Data source & features

// Guide: live source + provider; API or scraping (if scraping: ToS allows it AND a fallback).
// Update frequency. How much data exists today and how fast it grows. The label and where it
// comes from — MUST NOT be mechanically derivable from the features. Rare positive class.
// NAMED features. Leakage and out-of-time split.

*Source.* #TODO[Provider and endpoint], accessed via #TODO[API or scraping].
#TODO[If scraping: state that the ToS permits it and name a fallback source.]

*Update frequency and volume.* Updates every #TODO[interval].
#TODO[How much history exists today and how fast it grows. If history only begins when your
poller starts, say so explicitly — the guide asks for exactly this.]

*Label.* #TODO[What it is, where the ground truth comes from, and when it becomes known.]
It is not derivable from the features because #TODO[reason].

*Features.* #TODO[Name them. "Various features" scores low.]

*Leakage and splitting.* Out-of-time split: train #TODO[range], validate #TODO[range],
test #TODO[range]. #TODO[Where future information could leak in, and how you prevent it.]

= 4 System design

#figure(
  image("architecture.png", width: 94%),
  caption: [FTI architecture. The three pipelines are decoupled: they communicate only through
  the feature store and the model registry.],
)

*Tech stack.* One line each, as the guide requires:

#set list(spacing: 0.48em)
- *Feature store* — Hopsworks. #TODO[why]
- *Experiment tracking & registry* — MLflow. #TODO[why]
- *Orchestration* — GitHub Actions, scheduled. #TODO[why]
- *Serving* — Google Cloud Run + GCS. #TODO[why]

*Optional / stretch.* #TODO[Anything beyond core FTI — mark it explicitly optional.]

The repository is public and will remain reachable for the whole semester.
