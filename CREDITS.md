# Credits

Decompose is original work by Auny LLC, MIT licensed. It borrows ideas, not code. Each technique below is credited to its source.

| Technique | Source | Where it is used |
| --- | --- | --- |
| Topological layering | Arthur B. Kahn, "Topological sorting of large networks", Communications of the ACM 5(11), 1962 | Building parallel waves from dependencies and detecting cycles. |
| Critical path method | James E. Kelley Jr. and Morgan R. Walker, "Critical-path planning and scheduling", Eastern Joint Computer Conference, 1959 | The longest dependency chain printed with each plan. |
| Work and span bound | Richard P. Brent, "The parallel evaluation of general arithmetic expressions", Journal of the ACM 21(2), 1974 | The illustrative speedup bound `T1 / Tinf` in the picking reference. |
| Lead-and-workers and parallelization patterns | Anthropic, ["Building effective agents"](https://www.anthropic.com/research/building-effective-agents), 2024 | Splitting work across parallel workers and having one lead agent merge and check the results. |

No third-party code is bundled.
