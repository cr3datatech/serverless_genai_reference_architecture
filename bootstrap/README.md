# Bootstrap

One-time account setup, run by an administrator **before** the first `terraform apply`. These are things the stack can't safely do for itself: they define who may deploy it and how much may be spent, so they sit outside the stack's own permissions.

| Order | Step | Well-Architected pillar | What it does |
|-------|------|-------------------------|--------------|
| 1 | [iam/](iam/README.md) | Security | Least-privilege operator identity: MFA-gated deploy and review roles, plus a permissions boundary that caps every role the stack creates |
| 2 | [budget/](budget/README.md) | Cost Optimization | Account-level AWS Budget that emails alerts at 50%, 80% and 100% of a monthly limit, and on a forecast overrun |

Both steps take a few minutes in AWS CloudShell. Account-specific values (account ID, email address, limit) are supplied at run time and never stored in this repository.
