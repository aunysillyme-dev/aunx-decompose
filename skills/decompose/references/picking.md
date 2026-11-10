# Picking a model and a machine per unit

The helper never picks. It checks the map and leaves the `model`, `machine`
and `runner_up` columns for you. This page is the method. It assumes you can
see an inventory: the models you can call, and the machines you can run on.

## Grades

Grade every key on one ordinal scale: **H > M > UNK > L**. Grades are ranks,
not numbers. Unknown is never zero and never unlimited: a model whose usage
you cannot read is UNK, which ranks below a measured M and above a measured L.
A key that does not apply to a row ties with every grade.

## Model pick

**Filter first.** Drop a model when any of these holds:

- it lacks a capability the unit needs (web access, a logged-in browser, file
  writes), as shown by a live check, not by its documentation;
- a minimal live call to it fails, or it has no credit left;
- its known context window is smaller than the unit needs;
- a rule forbids it for this content (private data, a voice the user reserves
  for one model, a model the user only allows on request).

**Then rank, one key at a time.** Keep only the rows holding the best grade on
the current key, then move to the next. Stop when one row is left.

1. **Type fit.** The model's own description names the unit's type.
2. **Speed fit.** The model's tier equals the unit's speed (H), is one tier away
   (M) or two (L). When frontier models are request-only, a frontier unit takes
   the best standard model and you note which frontier model would have won.
3. **Wave spread.** Inside a parallel wave, drop families the wave already used
   while an unused family survives.
4. **Reliability.** Measured success on this type. Use your own logs first,
   then a primary-source benchmark, never an aggregator.
5. **Cost plus verify cost.** Price per task, plus what it costs you to check
   the output. Cheaper ranks higher.
6. **Expiry.** Credit or included usage that resets before the unit would
   finish ranks first, because unused capacity is waste.
7. **Headroom.** Usage left on the model's pool.
8. **Tool-first tie rule.** On a tie, prefer the external agent CLI over your
   own session's model, so your own window stays free for judgment.
9. **Context.** More of the window left ranks higher, then a larger window. A
   model whose context you cannot read is UNK and gets a flag in the pick line.
10. **Family spread.** Fewer units already on this family in the whole plan.
11. **Stable id.** Alphabetical, so no two rows ever tie.

Name the runner-up and two fallbacks from billing pools other than the pick's,
so one pool error never takes out both. Switch on silence or a credit error;
never wait on an exhausted model.

**Effort is separate from tier.** Set it from the unit, not the model: low,
medium or high from the unit's importance, raised to a floor by type (coding
at least high; security, irreversible and architecture work at the
highest regular level; review at least medium). Leave any special maximum
level to the user's choice. Clamp it to the model's levels.

**Review and test need a second family.** A unit that audits or tests work
never runs on a family that wrote any of that work.

## Machine pick

For each unit, read `needs` (cpu, ram_gb, gpu, disk_gb, minutes, local_only,
scale_up, capabilities).

1. **Filter.** Drop machines that cannot fit the needs, cannot be reached, or
   cannot hold the unit's data. `local_only` keeps a unit on your own machine.
2. **Money first.** Free capacity or credit that expires soon ranks first
   (within a week is a sensible default), then credit you already hold, then
   the cheapest metered option. Spending past held credit is the user's call.
3. **Smallest fit among money ties.** Pick the smallest machine that fits, so
   larger ones stay free for heavier units. A unit marked `needs.scale_up` is
   compute-bound: it takes the largest machine that fits instead.
4. **One machine per parallel unit.** Units in one wave go to different
   machines. Keep a `taken` list per wave and skip machines already in it while
   another fits.
5. **Name the runner-up**, and the key that decided between them.

A substep moves off its parent's machine when it outgrows it (memory above
about 80 percent, more CPUs than it has), or when the work is long enough that
starting another machine pays for itself. Tune that break-even from your own
run logs.

## Illustrative formulas

These help you reason about shapes and waves. They are model estimates to
calibrate against your own measurements, not results.

- **Serial work and critical path.** With `d(u)` the duration of unit `u`,
  serial time is `T1 = sum of d(u)`, and the critical path `Tinf` is the
  longest dependency chain by duration. Parallel waves can never beat `Tinf`,
  so the best possible speedup is `T1 / Tinf`. The helper prints both from
  your `needs.minutes`.
- **Width-limited waves.** If wave `k` holds `width_k` units and you can run
  `C_k` at once, that wave takes about `ceil(width_k / C_k)` times its longest
  unit. Add the waves for a plan estimate.
- **Fan-out break-even.** One call over N items costs about `o1 + N * t`. A
  fan-out of P workers costs about `oP + ceil(N / P) * (c + t)`, with `o` the
  start-up overhead, `c` the per-item overhead and `t` the time per item. Fan
  out when the second is smaller. The default thresholds in the plan come from
  this inequality with guessed overheads; replace the guesses with yours.
- **Advisor pay-off.** A review that takes `t_adv` pays for itself when the
  critical-path time it is expected to save is larger than `t_adv`. That is why
  the gate fires on large or serial maps and stays quiet on small ones.
