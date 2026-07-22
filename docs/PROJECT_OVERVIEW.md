# AI in Austere Medicine Project

The AI in Austere Medicine Project is an open-source research initiative developing guideline-grounded clinical decision support for austere, remote, and resource-limited environments.

The project's primary development platform is **EdgeCDSS**.

EdgeCDSS is released under the MIT License. Source code, documentation, and development are public to encourage transparency, independent review, collaboration, and reproducible research.

Recent research increasingly supports clinical AI systems that combine evidence retrieval, deterministic validation, and human oversight rather than relying solely on autonomous large language models.¹⁻⁴

## Open

- MIT licensed.
- Open-source development.
- Public documentation.
- Community testing, feedback, and contributions are encouraged.

## Deterministic

EdgeCDSS uses deterministic software whenever a task can be solved reliably in code.

Medication calculations, contraindication checks, patient context, structured clinical logic, and safety gates are performed by deterministic Python code.

Artificial intelligence is restricted to:

- language generation;
- retrieval support;
- semantic validation.

This deterministic-first architecture aligns with emerging recommendations that safety-critical clinical functions remain transparent, testable, independently verifiable, and subject to human oversight.¹⁻³

## Research

EdgeCDSS is a research prototype.

It has not been validated for clinical use and must not be used to diagnose, treat, or manage real patients.

Testing should be performed using simulated, fictional, or synthetic scenarios only.

Consistent with current guidance for clinical AI systems, prospective evaluation, transparent reporting, and ongoing validation are necessary before deployment in patient care.²⁻⁴

## EdgeCDSS Version 4.0

Version 4.0 introduces a new system architecture designed for edge deployment and open research.

### Architecture

- Self-hosted on an NVIDIA Jetson Orin Nano.
- Opportunistic connectivity over any available network — low-earth-orbit satellite, LTE/5G, Wi-Fi, or broadband — with remote access through an outbound-only encrypted tunnel.
- Retrieval-Augmented Generation (RAG) with an on-device vector database.
- Deterministic-first clinical pipeline.
- AI restricted to language generation and semantic validation.
- Structured clinical feedback and audit logging.
- Automated regression testing.

Retrieval-Augmented Generation (RAG) improves factual grounding by retrieving authoritative clinical guidance during inference instead of relying solely on information encoded within a language model.⁴

### Design Goals

- Open-source and reproducible.
- Transparent system architecture.
- Deterministic safety wherever possible.
- Edge-first deployment.
- Community-driven development.
- Continuous testing and evaluation.

## Research Focus

Current research includes:

- Guideline-grounded clinical decision support.
- Edge computing.
- Off-grid and remote medical infrastructure.
- Retrieval-Augmented Generation (RAG).
- Clinical safety validation.
- Human-AI interaction.
- Offline and hybrid AI architectures.
- Open-source medical AI research.

## Related Work

The design philosophy behind EdgeCDSS reflects current research supporting retrieval-grounded generation ([Lewis et al., 2020](https://arxiv.org/abs/2005.11401)) and human-supervised clinical AI ([Sutton et al., 2020](https://www.nature.com/articles/s41746-020-0221-9)) rather than autonomous large language model (LLM)-based decision making. Recent evaluations of LLM clinical knowledge ([Singhal et al., 2023](https://www.nature.com/articles/s41586-023-06291-2)) and of LLM inference on low-power edge hardware ([arXiv, 2025](https://arxiv.org/html/2511.07425v1)) inform the boundaries this architecture is built around, with risk management guided by the [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework).

Rather than treating an LLM as the source of clinical reasoning, EdgeCDSS combines deterministic clinical logic, retrieval from authoritative clinical guidelines, structured validation, and constrained language generation within a transparent and auditable architecture.

Representative literature includes:

- Foundation models for medical AI and clinician-supervised deployment.
- Clinical evaluation of large language models in medicine.
- Retrieval-Augmented Generation (RAG) for evidence-grounded AI systems.
- Human factors and trustworthy AI in healthcare.
- FDA lifecycle guidance for AI-enabled medical software.

Collectively, this body of work supports:

- deterministic clinical pipelines;
- guideline-grounded decision support;
- retrieval-grounded inference;
- human oversight;
- continuous validation;
- transparent documentation;
- auditability;
- lifecycle monitoring.

## Project Commitments

The AI in Austere Medicine Project is committed to:

- Developing in the open under the MIT License.
- Publishing significant architectural changes.
- Publicly documenting data collection practices.
- Collecting only the minimum data necessary for research and operation.
- Discouraging the submission of PHI, PII, or real patient information.
- Supporting responsible vulnerability disclosure.
- Encouraging independent review and community participation.
- Publishing limitations and known issues alongside project updates whenever practical.
- Maintaining human oversight in all clinical decision-making.
- Improving the project through testing, evidence, and community feedback.

## References

1. Moor M, Banerjee O, Abad ZSH, Krumholz HM, Leskovec J, Topol EJ, Rajpurkar P. Foundation models for generalist medical artificial intelligence. *Nature*. 2023;616(7956):259–265.
2. Lee P, Bubeck S, Petro J. Benefits, Limits, and Risks of GPT-4 as an AI Chatbot for Medicine. *N Engl J Med*. 2023;388(13):1233–1239.
3. U.S. Food and Drug Administration. Artificial Intelligence-Enabled Device Software Functions: Lifecycle Management and Marketing Submission Recommendations. Draft Guidance. 2025.
4. Lewis P, Perez E, Piktus A, et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *Advances in Neural Information Processing Systems (NeurIPS)*. 2020.
5. *Placeholder:* peer-reviewed literature from npj Digital Medicine, JAMIA, and The Lancet Digital Health evaluating retrieval-grounded clinical AI, LLM safety, and trustworthy deployment (2024–2025) — to be replaced with specific verified papers.
