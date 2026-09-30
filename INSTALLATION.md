# Installation status

Phase 0 is documentation only. No install/start/login/demo command exists yet.

After approval, pin compatible Node.js, Python, PostgreSQL and Keycloak versions with lockfiles. Proposed Windows setup uses Docker Desktop/WSL2 or equivalent containers. Ollama is optional until Phase 13; model choice depends on evaluated quality and available RAM/VRAM.

Planned sequence: copy empty environment template to ignored local file; generate unique local secrets; start services; migrate with migration-only role; bootstrap first administrator through audited one-time local operation; explicitly load synthetic environment; run health and authorization tests. No default password ships. Actual commands will be documented only after verification.

Production packaging requires TLS, backups, monitoring, restore procedures and key management. Do not enter production credentials during development.

Vercel CLI is not installed. If Vercel is later selected, strongly recommend `npm i -g vercel` for environment management, deployments and logs. It is not required by the proposed local-first design and was not installed here.
