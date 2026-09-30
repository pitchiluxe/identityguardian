# MASTER BUILD PROMPT — IDENTITYGUARDIAN AI

You are the Principal IAM Architect, Identity Security Engineer, Full-Stack Architect, AI Engineer, DevSecOps Engineer, UX Architect, and QA Lead responsible for designing and building a new platform called:

# IdentityGuardian AI

**Autonomous Identity Intelligence, Governance & Security Platform**

Your objective is to create an enterprise-grade Identity and Access Management platform that combines IAM administration, identity governance, identity security, access intelligence, AI-assisted investigation, identity attack-path analysis, machine identity governance, AI-agent governance, and hands-on IAM simulation.

This must NOT be a simple CRUD IAM dashboard.

Build a platform capable of answering:

> Who has access to what, why do they have it, how did they obtain it, when was it granted, are they still using it, should they still have it, what could they potentially reach through it, and what would happen if that access were changed?

The system must provide evidence for its conclusions.

AI must assist administrators but must not silently make consequential IAM changes.

Use the principle:

**AI investigates → AI explains → AI recommends → system simulates → authorized human approves → controlled action executes → everything is audited.**

---

# 1. IDENTITY DIGITAL TWIN

Create a dynamic identity graph representing the organization's identity environment.

Model:

* Employees
* Contractors
* Guests
* Administrators
* Service accounts
* Workload identities
* Applications
* AI agents
* Groups
* Nested groups
* Roles
* Permissions
* Devices
* Authentication methods
* SaaS applications
* API keys
* Certificates
* Cloud resources
* Databases
* Servers
* Privileged accounts
* Departments
* Managers
* Business units

Represent relationships visually.

Example:

Employee
→ Department
→ AD Group
→ Nested Group
→ Entra Role
→ Application
→ Database
→ Sensitive Resource

Administrators must be able to click any node and inspect its relationships.

Support graph queries such as:

"Show every path between this contractor and production."

"Which identities can indirectly reach payroll?"

"Which service accounts have privileged access?"

---

# 2. WHY DOES THIS PERSON HAVE ACCESS?

Create an Access Explanation Engine.

For every entitlement, determine its origin.

Possible origins:

* Direct assignment
* Group membership
* Nested group
* Role assignment
* RBAC policy
* ABAC policy
* Temporary privilege
* Application role
* Legacy entitlement
* Service-account delegation
* Manager approval
* Automated provisioning
* Unknown/orphaned assignment

Display an Access Chain.

Example:

Erick
→ IT Support
→ HelpDesk-L2
→ Azure Support Role
→ User Administration
→ Password Reset

Display:

* entitlement
* source
* approver
* date granted
* expiration
* last used
* associated ticket
* business justification
* risk indicators

---

# 3. IDENTITY ATTACK-PATH SIMULATOR

Build a defensive identity attack-path analysis engine.

It must NOT exploit systems.

Instead, analyze IAM relationships and determine possible privilege escalation or lateral-access paths.

Example:

Compromised Help Desk User

↓

Password Reset Capability

↓

Privileged Employee

↓

Application Administrator

↓

Cloud Resource

↓

Sensitive Database

Visualize the path.

Show:

* starting identity
* intermediary permissions
* privilege transitions
* sensitive destination
* risk factors
* recommended defensive controls

Allow administrators to simulate:

"What happens if this identity is compromised?"

---

# 4. PRIVILEGE CREEP RADAR

Create a system that detects accumulated access.

Track identity access history.

Example:

2023 — Help Desk

2024 — System Administrator

2025 — Cloud Engineer

2026 — Security Engineer

Determine whether permissions from previous roles remain.

Detect:

* unused permissions
* duplicate permissions
* historical access
* inherited privileges
* excessive group membership
* role mismatches
* dormant administrator privileges

Create an Access Evolution Timeline.

---

# 5. AI ACCESS REVIEW INVESTIGATOR

Replace basic access certification screens with evidence-driven reviews.

For every review provide:

* employee role
* department
* manager
* resource
* entitlement
* entitlement source
* last usage
* frequency of usage
* privilege level
* comparable employees
* access history
* associated ticket
* business justification
* risk indicators

AI may recommend:

KEEP

REVIEW

REMOVE

But the AI recommendation must be accompanied by evidence and uncertainty.

Final approval remains with an authorized human.

---

# 6. IAM WHAT-IF ENGINE

Create a change simulation environment.

Before making an IAM change, administrators can ask:

"What happens if I remove this user from this group?"

"What happens if Finance loses this application role?"

"What happens if this administrator leaves?"

"What happens if this service account is disabled?"

"What happens if this role is modified?"

The engine must calculate downstream dependencies.

Show:

* applications affected
* users affected
* resources affected
* workflows affected
* potential lockouts
* privilege reduction
* security improvement
* operational impact

NO production changes occur during simulation.

---

# 7. JUST-IN-TIME PRIVILEGE BROKER

Create temporary privileged access workflows.

Example:

Engineer requests:

Production Database Administrator

Duration:

2 hours

Reason:

Incident INC-2026-4812

Evaluate:

* identity
* role
* device
* authentication strength
* requested resource
* duration
* business justification
* policy
* historical behavior

Route through appropriate approval controls.

When approved:

grant temporary privilege.

When duration expires:

automatically revoke it.

Record everything in audit logs.

---

# 8. MACHINE IDENTITY GUARDIAN

Create dedicated governance for non-human identities.

Support:

* service accounts
* API keys
* OAuth clients
* workload identities
* certificates
* automation accounts
* Kubernetes service accounts
* bots
* CI/CD identities

Track:

OWNER

PURPOSE

CREATED

LAST USED

CREDENTIAL AGE

EXPIRATION

PERMISSIONS

DEPENDENCIES

RISK INDICATORS

Detect orphaned machine identities.

---

# 9. AI-AGENT IDENTITY GOVERNANCE

AI agents must be treated as identities.

Every AI agent receives:

* unique identity
* owner
* department
* purpose
* model
* allowed tools
* allowed applications
* allowed APIs
* permitted data
* prohibited data
* maximum privilege
* credential scope
* expiration
* activity history

Create an:

AI Agent Identity Registry.

Allow queries such as:

"Which agents can access customer information?"

"Which agents can send email?"

"Which agents can modify production?"

"Which agents have credentials?"

"Which agents have excessive privileges?"

---

# 10. IDENTITY RISK STORY

Never present unexplained risk scores.

Every risk assessment must provide evidence.

Instead of:

Risk = 87

display:

HIGH IDENTITY EXPOSURE

Reasons:

* Privileged role assigned
* Dormant entitlement detected
* Authentication control recently changed
* Access inherited through nested groups
* Identity can reach sensitive resources
* Previous-role privileges remain

Allow administrators to expand every finding and inspect the evidence.

---

# 11. JOINER / MOVER / LEAVER INTELLIGENCE

Create automated identity lifecycle workflows.

## JOINER

Employee created.

Determine:

* department
* manager
* job title
* location
* employment type

Recommend baseline access.

Require appropriate approvals.

Provision accounts.

Record evidence.

## MOVER

Employee changes roles.

Compare:

OLD ROLE

versus

NEW ROLE

Identify:

permissions to retain

permissions to review

permissions potentially requiring removal

new access required

privilege conflicts

## LEAVER

Employee termination workflow.

Identify:

* Active Directory account
* Entra account
* SaaS accounts
* sessions
* tokens
* API keys
* privileged memberships
* application ownership
* service-account ownership
* shared resources
* outstanding approvals

Provide a controlled deprovisioning workflow.

---

# 12. IDENTITY TIME MACHINE

Create historical identity reconstruction.

Administrator selects:

IDENTITY

DATE

TIME

System reconstructs effective access at that moment.

Example:

"Show everything this administrator could access at 2:14 PM on September 18, 2026."

Display:

roles

groups

permissions

applications

privileged access

machine relationships

authentication state where historical data supports it

resource relationships

This should support incident investigation and auditing.

---

# 13. NATURAL-LANGUAGE IAM INVESTIGATOR

Create an AI IAM assistant.

Prefer local AI through Ollama where practical.

Allow questions such as:

"Show terminated employees with remaining access."

"Find contractors with privileged roles."

"Find administrator accounts that have not been used recently."

"Who can access payroll?"

"Why does Erick have access to Azure?"

"Show identities with access to production."

"Which service accounts have no owner?"

"Show risky access paths."

Convert natural language into safe internal queries.

IMPORTANT:

AI must never invent IAM information.

Responses must be grounded in retrieved IAM data.

Display the evidence used to construct the response.

---

# 14. POLICY-AS-CODE GENERATOR

Administrators should be able to describe IAM policies using natural language.

Example:

"Contractors cannot have permanent Global Administrator access."

The AI generates a proposed machine-readable policy.

Show:

POLICY NAME

PURPOSE

SCOPE

CONDITIONS

ACTION

EXCEPTIONS

TESTS

Before activation:

validate syntax

test policy

simulate against Identity Digital Twin

show affected identities

show operational impact

request approval

Only then allow authorized deployment.

---

# 15. IAM TRAINING & SIMULATION LAB

Create an integrated IAM training environment.

This is critical.

Provide a simulated enterprise called:

CONTOSO GLOBAL TECHNOLOGIES

Create departments:

IT

Security

Finance

Human Resources

Sales

Engineering

Operations

Executive

Create realistic:

employees

contractors

managers

administrators

service accounts

applications

groups

roles

permissions

tickets

incidents

Simulate:

Active Directory

Microsoft Entra ID

Okta-style SSO

MFA

RBAC

SSO

SCIM

SAML

OAuth/OIDC

PAM

IGA

JML

Access Reviews

ServiceNow-style tickets

Create labs covering:

User onboarding

Password reset

Account lockout

Group management

RBAC

MFA registration

Conditional access

SSO configuration

Access review

Privileged access

Service account governance

Employee termination

Role transfer

Privilege creep

Incident investigation

Attack-path investigation

---

# OLLAMA AI INSTRUCTOR

Integrate Ollama as the primary local instructor for Lab Mode.

The AI instructor must NOT simply complete exercises.

Instead it should:

observe the student's work

validate configuration

identify errors

explain concepts

provide hints

ask troubleshooting questions

evaluate completed work

generate final lab reports

Example:

Student incorrectly configures an SSO policy.

Instructor:

"Your authentication flow is failing between the identity provider and service provider. Inspect the assertion configuration and compare the expected attributes."

Do NOT immediately provide the answer.

---

# ENTERPRISE CONNECTORS

Design a connector architecture capable of eventually integrating with systems such as:

Microsoft Active Directory

Microsoft Entra ID

Okta

AWS IAM

Google Workspace

GitHub

ServiceNow

Slack

HRIS systems

PAM platforms

SaaS applications

For development, build mock/sandbox connectors first.

Never require real production credentials to demonstrate the platform.

---

# SECURITY ARCHITECTURE

Security must be built into the application.

Implement:

RBAC

least privilege

MFA-ready authentication

secure sessions

encrypted secrets

audit logging

API authorization

rate limiting

input validation

CSRF protection where applicable

secure headers

database access controls

environment-variable management

secret rotation architecture

Do NOT hardcode credentials.

Create:

.env.example

Never commit:

.env

.env.local

API keys

passwords

tokens

certificates

---

# SAFETY CONTROLS

Consequential IAM operations require human authorization.

Examples:

Disable account

Delete account

Remove administrator role

Modify privileged group

Revoke credential

Modify production policy

Terminate session

Rotate production credential

The AI may recommend these actions but must not silently execute them.

Provide:

SIMULATE

REVIEW

APPROVE

EXECUTE

ROLLBACK

where technically appropriate.

---

# USER INTERFACE

Build a premium enterprise cybersecurity interface.

Primary navigation:

Dashboard

Identity Graph

Identities

Access

Applications

Privilege Radar

Attack Paths

Access Reviews

JIT Access

Machine Identities

AI Agents

Lifecycle

What-If Simulator

Time Machine

Policies

Investigations

Labs

Reports

Audit Logs

Integrations

Administration

AI Assistant

Use professional data visualizations.

Identity Graph must be interactive.

Attack paths must be visual.

Privilege creep should have timelines.

Access reviews should provide evidence panels.

---

# DASHBOARD

Display meaningful operational information such as:

Total Identities

Human Identities

Machine Identities

AI Agents

Privileged Identities

Dormant Accounts

Orphaned Accounts

Orphaned Service Accounts

Pending Reviews

Temporary Privileges

Policy Violations

Privilege Creep Findings

Identity Exposure Findings

Attack Paths

JML Events

Do not fill production screens with meaningless random statistics.

Demo mode may use seeded realistic data clearly labeled as simulated.

---

# AI ARCHITECTURE

Primary local AI:

Ollama

Support configurable models.

Create an abstraction layer so additional providers can be integrated later.

AI must use retrieved IAM evidence rather than model memory for organization-specific conclusions.

Implement a pattern similar to:

USER QUESTION

↓

INTENT PARSER

↓

IAM QUERY PLANNER

↓

AUTHORIZED DATA RETRIEVAL

↓

IDENTITY GRAPH / DATABASE

↓

EVIDENCE COLLECTION

↓

LLM REASONING

↓

ANSWER

↓

EVIDENCE DISPLAY

↓

OPTIONAL RECOMMENDATION

↓

SIMULATION

↓

HUMAN APPROVAL

---

# DATA ARCHITECTURE

Design entities for:

User

Identity

Account

Group

Role

Permission

Entitlement

Application

Resource

Device

AuthenticationMethod

ServiceAccount

MachineIdentity

AIAgent

Credential

Certificate

AccessRequest

Approval

AccessReview

Policy

RiskFinding

AttackPath

Incident

Ticket

Department

Manager

EmploymentEvent

AuditEvent

Lab

LabAttempt

Connector

Integration

HistoricalSnapshot

Relationship

Design both current-state and historical data models.

---

# GRAPH ARCHITECTURE

The Identity Digital Twin should support graph relationships.

Example relationships:

USER_MEMBER_OF_GROUP

GROUP_INHERITS_GROUP

GROUP_HAS_ROLE

ROLE_HAS_PERMISSION

PERMISSION_ACCESS_RESOURCE

USER_OWNS_SERVICE_ACCOUNT

SERVICE_ACCOUNT_ACCESS_APPLICATION

AI_AGENT_USES_TOOL

AI_AGENT_ACCESS_DATA

DEVICE_USED_BY_USER

APPLICATION_TRUSTS_IDP

Use a graph abstraction that can initially operate using the selected database architecture but can later support a dedicated graph database.

---

# AUDITABILITY

Every sensitive action should record:

WHO

WHAT

WHEN

WHERE APPROPRIATE, SOURCE CONTEXT

TARGET

PREVIOUS STATE

NEW STATE

JUSTIFICATION

APPROVAL

RESULT

CORRELATION ID

Never allow AI-generated explanations to overwrite original audit evidence.

---

# REPORTING

Generate reports such as:

Identity Exposure Report

Privileged Access Report

Dormant Identity Report

Machine Identity Report

AI Agent Governance Report

Access Review Report

JML Report

Privilege Creep Report

Attack Path Report

Policy Compliance Report

Lab Completion Report

Support export where appropriate.

---

# GITHUB PORTFOLIO MODE

Because this application can also serve as an IAM engineering portfolio project, create documentation suitable for GitHub.

Generate:

README.md

ARCHITECTURE.md

SECURITY.md

THREAT_MODEL.md

INSTALLATION.md

DEMO.md

LABS.md

ROADMAP.md

CONTRIBUTING.md

CHANGELOG.md

Create:

docs/screenshots/

docs/videos/

Reserve placeholders for screenshots and demonstration videos.

README should explain:

Problem

Solution

Architecture

Features

IAM concepts demonstrated

Security controls

AI architecture

Screenshots

Demo workflow

Installation

Future roadmap

---

# DEVELOPMENT DOCUMENTATION

Create:

CLAUDE.md

AGENTS.md

PROMPT.md

ARCHITECTURE.md

DATABASE.md

UI.md

SECURITY.md

ROADMAP.md

TESTING.md

API.md

INTEGRATIONS.md

LABS.md

---

# SPECIALIZED DEVELOPMENT AGENTS

Create separate agent instructions for:

IAM Architect Agent

Identity Security Agent

Backend Agent

Frontend Agent

Database Agent

Graph Intelligence Agent

AI/RAG Agent

Integration Agent

DevSecOps Agent

QA Agent

Threat Modeling Agent

UX Agent

Lab Instructor Agent

Documentation Agent

Do not allow agents to overwrite each other's work blindly.

---

# BUILD PHASES

Do NOT attempt the entire system in one uncontrolled coding pass.

## PHASE 0

Requirements

Architecture

Threat model

Repository structure

Database schema

Design system

Security boundaries

## PHASE 1

Authentication

RBAC

Organizations

Users

Audit framework

Database

Application shell

## PHASE 2

Identity Digital Twin

Identity ingestion

Graph relationships

Identity profiles

Access explorer

## PHASE 3

Access Explanation Engine

Effective permission calculation

Entitlement lineage

## PHASE 4

Privilege Creep Radar

Access history

Dormant privileges

Access timeline

## PHASE 5

Attack Path Simulator

Graph traversal

Exposure paths

Defensive recommendations

## PHASE 6

Access Review Investigator

Evidence collection

Review workflow

AI recommendations

Human approval

## PHASE 7

What-If Engine

Change simulation

Dependency analysis

Impact reports

## PHASE 8

JIT Privilege Broker

Temporary elevation

Approval

Expiration

Revocation

## PHASE 9

Machine Identity Guardian

Service accounts

Credentials

Certificates

Ownership

## PHASE 10

AI-Agent Governance

Agent registry

Agent permissions

Tool access

Data boundaries

## PHASE 11

JML Intelligence

Joiner

Mover

Leaver

## PHASE 12

Identity Time Machine

Historical snapshots

Historical reconstruction

## PHASE 13

Natural-Language Investigator

Ollama

IAM query planner

Evidence grounding

## PHASE 14

Policy-as-Code

Policy generation

Testing

Simulation

Approval

## PHASE 15

IAM Simulation Lab

Enterprise simulator

IAM scenarios

Ollama instructor

Scoring

Reports

## PHASE 16

Enterprise connectors

Start with sandbox/mock implementations.

## PHASE 17

Reporting

Compliance evidence

Exports

## PHASE 18

Security hardening

Penetration testing

Authorization testing

Threat-model validation

## PHASE 19

Performance

Graph optimization

Database optimization

Caching

## PHASE 20

Production packaging

Docker

Deployment documentation

Monitoring

Backups

Recovery

---

# TESTING REQUIREMENTS

Implement:

Unit tests

Integration tests

API tests

Authorization tests

RBAC tests

Graph tests

Policy tests

Simulation tests

AI grounding tests

Hallucination-resistance tests

Audit tests

Connector tests

End-to-end tests

Particularly test privilege boundaries.

A normal user must NEVER be able to manipulate requests to gain administrator functionality.

---

# DEMO INCIDENT

Seed the demo environment with a realistic IAM investigation.

Example:

An IT Support employee previously worked in another department.

Legacy group membership remains.

That membership grants indirect access to an administrative application.

Another nested group provides additional privileges.

The employee does not realize the access remains.

IdentityGuardian should:

detect the access

construct the identity graph

identify privilege creep

calculate effective access

show the access origin

construct relevant attack/exposure paths

produce a Risk Story

recommend review

allow What-If removal simulation

show dependencies

request human approval

remove access only in the simulated environment

record the event

allow Time Machine reconstruction afterward

This scenario should demonstrate multiple platform capabilities working together.

---

# IMPORTANT ENGINEERING RULE

Do not create fake buttons.

Every visible control should either:

WORK,

be clearly marked DEMO,

or be clearly marked PLANNED.

Do not claim integrations are working unless they actually work.

Do not fabricate AI analysis.

Do not fabricate security findings.

Do not expose credentials.

Do not automatically execute dangerous IAM changes.

Do not break working functionality while implementing new phases.

Before each phase:

1. inspect existing architecture
2. identify dependencies
3. create implementation plan
4. implement
5. test
6. run security checks
7. verify existing features still work
8. document changes
9. commit the completed phase

---

# FINAL PRODUCT VISION

IdentityGuardian AI should eventually provide one place where an organization can understand:

WHO an identity is

WHAT it can access

WHY it has access

HOW it obtained access

WHEN access changed

WHETHER access is still necessary

WHAT an attacker could potentially reach

WHAT would happen if access changed

WHICH machine identities exist

WHICH AI agents have access

WHICH policies are being violated

WHAT historical access existed during an incident

and

WHAT authorized administrators should investigate next.

Build IdentityGuardian AI as an explainable, evidence-driven identity intelligence platform rather than another IAM administration dashboard.

Start with PHASE 0.

Do not begin writing production code until the Phase 0 architecture, threat model, database model, identity graph model, repository structure, technology decisions, security boundaries, and implementation roadmap have been presented for review.
