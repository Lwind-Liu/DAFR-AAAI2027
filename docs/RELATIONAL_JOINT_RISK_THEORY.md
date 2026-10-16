# Joint-risk surface: scope and theoretical justification

For a fixed action, evidence revision and set of verified fields, each causal
path is a conjunction of primitive adverse events. Harm is the union of those
paths. Independent primitive events give a multilinear polynomial obtained by
inclusion-exclusion. Shared primitive events appear once in an intersection
term, so shared paths are correlated even when the primitive events are
independent. The method is not an additive sum of path losses.

The finite-world oracle multiplies event/non-event probabilities for each
assignment and sums the mass of harmful assignments. Inclusion-exclusion and
enumeration are equivalent under the declared event semantics. This equivalence
is checked against independent oracle code and retained execution traces.

A single path with two events already has a curved boundary: p*q <= b.
With b=0.1, points (0.9, 0.1) and (0.1, 0.9) are safe, but their midpoint
(0.5, 0.5) is unsafe. An affine-threshold safe region is convex, so no single
affine threshold can exactly reproduce this safe set. The surface can express
the combination without assigning high risk to either primitive in isolation.
This example concerns representation, not universal superiority on all tasks.

For a fixed positive-severity union model, risk is monotone in each primitive
probability. If probability estimates have valid independent-event semantics
and coordinate-wise coverage bounds, evaluating the upper/lower corners
provides monotone risk bounds. The current Flash experiment uses declared
point probabilities; it does not estimate or validate such coverage in business
data. Correlation between primitive events requires a joint event distribution
or a different bound; the present polynomial must not assume it away silently.

Scoped verification removes an applicable path only when issuer, effect,
field, value and evidence revision match. A changed action or revision requires
new evidence. Complexity is exponential in path count for inclusion-exclusion;
the experiments have two paths and at most five primitive events. Larger
graphs would require factorization, compiled Boolean models, or other exact/
bounded inference implementations.

The Flash results test the upgraded relational surface with typed adapters,
not the original convex risk cone or its production text encoder. They support
controlled representation and topology-transfer claims. They do not establish
the empirical truth of a real-world causal graph, real-world probability
calibration, or updated performance on unchanged historical benchmark tables.
