// Milestone summary template — MLOps HS26
// Used three times: docs/ms2_summary.pdf, ms3_summary.pdf, ms4_summary.pdf
//
//   cp docs/src/ms_summary_template.typ docs/src/ms2_summary.typ
//   typst compile docs/src/ms2_summary.typ docs/ms2_summary.pdf
//
// RULES (Milestone Summary Guide):
//   * max 2 pages, PDF, committed BEFORE 23:59 on the deadline (last commit is graded)
//   * graded as its own criterion: "Summary & Response to Reviews"
//   * BOTH sections are required
//   * Section 2 must answer EVERY distinct point from BOTH reviews AND the editorial
//     summary. One numbered entry each: A1.. (Reviewer A), B1.. (Reviewer B), E1.. (editors).
//     Same point from both reviewers -> answer once, name both labels.
//     Status per entry: Changed / Partly / Rejected / Not yet.
//     Point to the commit or file for anything you changed.
//     A reasoned rebuttal is fine. SILENCE COSTS MARKS.
//
// Common mistakes: points skipped · "fixed" with no commit or file · summary copied from the
// README · responding to only one reviewer.

#let TODO(body) = text(fill: rgb("#c2352b"), weight: "semibold")[[#body]]

#let entry(label, title, status, body) = block(above: 0.55em, below: 0.55em)[
  *#label · #title* — #text(weight: "semibold")[#status] \
  #body
]

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
#show heading.where(level: 1): it => block(above: 0.9em, below: 0.5em)[
  #set text(11pt, weight: "bold")
  #it.body
]

#block[
  #set text(15pt, weight: "bold")
  MS#TODO[n] Summary — #TODO[project title]
]
#v(-0.3em)
#block[
  #set text(9pt, fill: luma(80))
  Kiana Kiser · MLOps HS26 · I.BA_MLOPS · #TODO[repo URL] · #TODO[date]
]
#v(0.25em)
#line(length: 100%, stroke: 0.5pt + luma(180))

= 1 What I achieved in this milestone

// Guide: bullets in your own words. What works now that did not before? Key decisions and
// why. What should a reviewer look at FIRST (files, dashboards, endpoints)? Be honest about
// what cost you (rows, accuracy, a rewrite). For MS4: what changed since MS3.

- #TODO[What works now that did not before.]
- #TODO[A key decision, and why you made it that way.]
- #TODO[What cost you — rows lost, a rewrite, accuracy given up. Honesty scores here.]

*Start here, reviewer.* #TODO[The two or three files / dashboards / endpoints a reviewer
should open first, and what to look for in each.]

= 2 Response to MS#TODO[n−1] reviews

// EVERY distinct point from both reviews AND the editorial summary gets its own entry.
// Delete the examples below; keep the shape.

#entry("A1", TODO[reviewer A's point, in your words], "Changed",
  [#TODO[What you did, and the commit hash or file path that proves it.]])

#entry("A2, B1", TODO[a point both reviewers raised — answer once, name both labels], "Partly",
  [#TODO[What you did do, and what you deliberately left.]])

#entry("B2", TODO[reviewer B's point], "Rejected",
  [#TODO[Why you disagree. A reasoned rebuttal is explicitly fine — an unanswered point is not.]])

#entry("E1", TODO[point from the editorial summary], "Not yet",
  [#TODO[Why not yet, and when it lands.]])

#v(0.4em)
#block(
  fill: luma(247),
  inset: 7pt,
  radius: 3pt,
  width: 100%,
)[
  #set text(8pt, fill: luma(80))
  *Before committing:* every point from both reviews and the editorial summary has an entry ·
  every "Changed" names a commit or file · under 2 pages · committed before 23:59 ·
  not a copy of the README.
]
