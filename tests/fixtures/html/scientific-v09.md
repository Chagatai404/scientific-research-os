# Scientific rendering regression

## Normalized shower profile

**A bold statement with *nested emphasis*** and Unicode α, β, Δ.
Inline $x_i^2$, alternate \(E_{\mathrm{vis}}\), and code `x_i ** 2`.

\[
\begin{aligned}
f(t)&=\frac{b(bt)^{a-1}e^{-bt}}{\Gamma(a)},\\
\int_0^\infty f(t)\,dt&=1\qquad(a,b>0).
\end{aligned}
\]

$$
\Sigma=\begin{pmatrix}\sigma_a^2&\rho\sigma_a\sigma_b\\\rho\sigma_a\sigma_b&\sigma_b^2\end{pmatrix}
$$

> [!formula] Domain matters
> The origin is $t=0$; changing the origin changes the fitted parameters.

1. Explain the dimensionless depth.
   - Connect to [[Radiation length|prerequisite]].
2. Predict the effect of $b$.

| Quantity | Meaning |
| --- | --- |
| $a$ | Shape |
| $b$ | Inverse depth scale |

![Profile](resource:profile "Normalized model, not measured data")

<!-- ros-question: normalization -->

## Return checkpoint

The source must survive rendering unchanged. Unsupported $\unknownmacro{x}$
must remain visible with a diagnostic.
