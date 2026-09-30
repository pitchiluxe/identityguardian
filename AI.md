# Grounded AI design

Ollama is the primary proposed local provider. Interface accepts task, authorized evidence, output schema, model configuration and cancellation; returns output, model version, latency and validation status. No database credentials, session tokens or write tools reach the model.

Pipeline: question → structured intent → authorized planner → allowlisted domain query → evidence bundle → optional model explanation → citation/claim checks → answer or insufficiency. Initial intents cover identity status/type, effective resource access, lineage, ownerless machines, dormant administrators and exposure paths. Ambiguous/unsupported requests require clarification; generated SQL, shell or code is never executed.

Deterministic engines calculate access, paths, counts, policies and impact. Model explains retrieved facts. Bundle includes IDs, scope, timestamps, coverage and rule/graph versions. Every organization-specific claim references evidence and is labeled fact, inference or recommendation. Reject invented/out-of-scope citations and unsupported numbers; fall back to a deterministic evidence summary. Citation validity alone cannot prove semantic truth, so output remains advisory.

Disclose model, evidence freshness and uncertainty as supported-scope complete, partial, conditional or insufficient. Do not invent confidence probabilities. If Ollama is offline, evidence queries remain available with “AI unavailable”; no canned analysis presented as model output.

Instructor receives scenario/rubric, learner changes and validator results. Hints progress from concept to diagnostic question to relevant setting. Worked solutions require explicit request or exercise completion. Instructor cannot change configuration or award scores; deterministic rubric does. Store model versions and validated responses separately from immutable evidence; apply access and retention policies.
