# FinePrint - Pitch Outline

## Slide 1: The Problem
- People sign contracts every day (employment, rent, services) that they cannot realistically read.
- Even if they read them, the implications of dense legal clauses are hard to spot.
- Hiring a lawyer for everyday contracts is inaccessible to most people.

## Slide 2: The Solution: FinePrint
- A multi-agent AI tool that reads any contract and finds hidden risks.
- Highlights clauses that quietly work against the signer.
- Explains the risk in plain English (or Hindi/Marathi) and provides a suggested counter-clause.

## Slide 3: Live Demo Walkthrough
- Drag and drop the Nimbus Employment contract.
- Watch the live agent team working in parallel (Profiler -> Readers -> Hunters -> Skeptic -> Advisor).
- See the resulting split-pane view, risk gauge, highlighted document, and "what to ask for instead".

## Slide 4: Why You Can Trust It
- **Grounding Guardrail:** Every single finding must quote the document verbatim. Our Python code verifies the quote exists; if it doesn't, the finding is dropped. No hallucinations.
- **The Skeptic:** An adversarial agent that tries to disprove other agents' findings before you see them. Rejected findings are shown transparently at the bottom.

## Slide 5: Roadmap
- Expanded language support (currently EN, HI, MR).
- OCR for scanned physical documents.
- Side-by-side comparison of two versions of a contract (e.g., comparing V1 with V2 after negotiations).

---

## 90-Second Demo Script
"Have you ever signed an employment contract or a lease without actually reading all 20 pages? You're not alone. We built FinePrint to fix this. Let me show you. 
I'm dragging in a standard employment agreement. Right away, you can see our team of AI specialists go to work. The Profiler identifies that we need to protect the employee. The Readers translate it to plain English, and our 5 Risk Hunters scan for hidden traps. 
Now, here's the magic. Notice the Grounding and Skeptic steps. FinePrint has a strict rule: if it can't quote the document character-for-character, the finding is deleted. Then, an adversarial Skeptic agent tries to disprove the remaining risks. It caught one here and rejected it because it's standard boilerplate.
Finally, we get our report. It highlights a training bond and a zero-day termination clause. And it doesn't just point out problems—it gives us exactly what to say to the employer to negotiate a better deal. FinePrint gives you clarity before you sign."
