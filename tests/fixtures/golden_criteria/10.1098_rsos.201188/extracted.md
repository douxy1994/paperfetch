---
title: "10.1098/rsos.201188"
authors: "Vaidya, Tushar, Murguia, Carlos, Piliouras, Georgios"
journal: "Royal Society Open Science"
doi: "10.1098/rsos.201188"
published: "2020/10/01"
source: "royalsocietypublishing_html"
has_fulltext: true
content_kind: "fulltext"
has_abstract: true
token_estimate: 8074
---

# 10.1098/rsos.201188

## Abstract

Black–Scholes (BS) is a remarkable quotation model for European option pricing in financial markets. Option prices are calculated using an analytical formula whose main inputs are strike (at which price to exercise) and volatility. The BS framework assumes that volatility remains constant across all strikes; however, in practice, it varies. How do traders come to learn these parameters? We introduce natural agent-based models, in which traders update their beliefs about the true implied volatility based on the opinions of other agents. We prove exponentially fast convergence of these opinion dynamics, using techniques from control theory and leader-follower models, thus providing a resolution between theory and market practices. We allow for two different models, one with feedback and one with an unknown leader.

## 1 Introduction

Econophysics divides into two paradigms. Statistical Econophysics relies on data, fitting certain power laws to existing asset prices at various time scales [1,2]. In statistical Econophysics, zero-intelligence agents have random interactions. Agents are homogeneous and have no learning ability. The central object of study is historical price data. The viewpoint is that interacting zero-intelligence traders’ actions are already incorporated into price fluctuations. The focus is on the macroscopic aggregation of interactions in the form of available data.
While this is an important area of research, agent-based Econophysics offers the opportunity to study the microscopic interactions in more detail, where agents are heterogeneous.
Our objective is to offer a cogent and clear motivation for agent-based Econophysics in the context of option volatilities, whereby learning and interaction are made explicit. To an outsider, it may seem that financial assets are observed at one price, decided by the market. In reality, prices fluctuate throughout the day and there is no equilibrium price: it is always in flux. Interaction between strategic traders and other players is embedded in all transactions and informational channels. Interaction is vital to understanding markets. The motivation for this paper was inspired by the works of Kirman [3] and Follmer *et al.* [4]. Rather than develop a thorough game theoretic or mean-field model, we advocate something in between. We aim to take a more nuanced view of agent-based Econophysics as espoused by Chakraborti *et al.* [5].

### 1.1 Our contribution

We introduce two different classes of learning models that converge to a consensus. Our interest is not in equilibrium but what process leads to it [6–8]. The first introduces a feedback mechanism (§[4.1](#s4a), theorem 4.1) where agents who are off the true ‘hidden’ volatility parameter feel a slight (even infinitesimally so) pull towards it along with the all the other ‘random’ chatter of the market. This model captures the setting where traders have access to an alternative trading venue or an information source provided by brokers and private message boards. The second model incorporates a market leader (e.g. Goldman Sachs) that is confident in its own internal metrics or is privy to client flow (private information) and does not give any weight to outside opinions (§[4.3](#s4c), theorem 4.4). Proving the convergence results (as well as establishing the exponentially fast convergence rates) requires tools from discrete dynamical systems. We showcase as well as complement our theoretical results with experiments (e.g. figure 2*a*–*d*), which for example show that if we move away from our models, convergence is no longer guaranteed.
We formalize the multi-dimensional analogues of our two models by using Kronecker products (§[5](#s5), theorems 5.1 and 5.3). Thus, our models show how a volatility curve could function as a global attractor given adaptive agents. We conclude the paper by discussing future work and connections to other fields.

## 2 Derivatives and social learning

Before discussing the main models of this paper, we give an overview of options markets and trading. We then motivate our framework and explain why certain social learning models are appropriate.

### 2.1 Trading

Most trading is done electronically. To be dominant, firms now invest huge sums in technology to get an edge. For futures trading, speed is vital to profits. Trading complex derivatives requires not only speed but huge amounts of investment in quantitative models. This, in turn, feeds the need for mathematicians, computer scientists and engineers. Increasingly, over the last two decades, the way trading is conducted has also seen drastic changes. Electronification of the markets has affected both instruments traded on and off exchange. Algorithmic trading drives not only plain vanilla instruments like stocks and futures but also derivatives [9–11]. Furthermore, the distinction between stock exchanges and over-the-counter (OTC) markets is not as clear as it once was [12]. In OTC markets, trading is between two counterparties and there is no centralized marketplace. Increasingly, over the last decade, there has been a regulatory push to make OTC markets more exchange-like. In OTC markets, participants may see what their competitors are quoting for a particular security, but volume and the actual price transacted remain the privy of the bilateral counterparties. In some quarters, OTC markets are usually referred to as being quote-driven or truly dark markets [13]. Regulation in the USA and European Union has resulted in fragmented exchange-based trading but centralization of opaque OTC markets.

### 2.2 Options markets

Derivative contracts are actively traded across the world’s financial markets with a total estimate value in the trillions of dollars. To get an intuitive understanding of the setting and the issues at hand, let us consider the prototypical example of European options.
A European option is the right to buy or sell an underlying asset at some point in the future at a fixed price, also known as the strike. A call option gives the right to buy an asset and a put option gives the right to sell an asset at the agreed price. On the opposite side of the buyer is the seller who has relinquished his control of exercise. Buyers of puts and calls can exercise the right to buy or sell. Sellers of options have to fulfil obligations when exercised against. The payoff of a buyer of a call option with stock price *S* T at expiry time
*T*and exercise price
*K*is max{
*S*
−
*T**K*, 0}, whereas for a put option is max{
*K*−
*S*, 0}.
*T**S*
0(e.g. $101), the exercise price
*K*(e.g. $90), the expiry
*T*(e.g. three months from today) and the volatility
*σ*in the Black–Scholes (BS) formula [14–16]:
1*K*= $90, $75, $60). If the underlying asset and the time to exercise
*T*(e.g. three months) are the same, one would expect the volatility to be the same at different strikes. In practice, however, the market after the 1987 crash has evolved to exhibit different volatilities. This rather strange phenomenon is referred to as the smile, or smirk (figure 1). Depending on the market, these smirks can be more or less pronounced. For instance, equity markets display a strong skew or smirk. A symmetric smile is more common in foreign exchange options markets. An excellent introduction to volatility smiles is given in [17].
How does the market decide what the quoted volatility should be (e.g. for a stock index three months from now)? This is a critical but not well-understood question. This is exactly what we aim to study by introducing models of learning agents who update their beliefs about the volatility. Agent-based models on volatility–smile interaction and formation have not been thoroughly addressed in finance or Econophysics. They remain a challenge [18]. Previous attempts have been made, but the focus has never been on the mathematical or specific nature of interaction [19,20]. Furthermore, our work takes into account the physicality of how trading occurs. An alternative perspective is offered in [21,22], again though the nature of interaction is missing. Nevertheless, these early attempts offer a good indication that at least the problem has garnered significant interest in different disciplines.

### 2.3 Econophysics

The challenge for physicists is not to force existing physics-based models on human behaviour but rather develop new models [23–25]. To go from local microscopic interactions to global macroscopic behaviour is not an easy task [26,27]. In fact, the choice of models seems infinite. There are a plethora of agent-based models [5,25,28]. Which one is correct? And, moreover, which type of social learning is representative of financial markets trading? LeBaron provides an early guide [29]. Agent-based models were proclaimed as the future for Econophysics [30,31]. While development in this area has been steady, the problem of the emergence of volatility smiles remains unresolved. The volatility smile is an active and vigorous area of research in the mathematical finance community [32–34]. Many models postulate a stochastic process for the underlying stock and volatility combined.

### 2.4 Knightian uncertainty

Risk and uncertainty are two different concepts [35–37]. Risky assets are those on which the probabilities of random events are well defined and known. For instance, suppose we observe historical data of a stock price. Are we confident to claim we know the distribution of the stock’s returns? If we are, then the stock is considered risky. Its risk is quantifiable. However, if we were unsure of even the correct probability measure, then we would be faced with uncertainty. In a sense, this captures the essence of financial markets. Traders and players use different probability measures when trading and quoting options. No single measure dominates. In fact, there are many models that are consistent with the observation of a finite number of strike volatilities in the market [38–41]. In practice, the choice of a correct probability measure such that a derivative contract is priced correctly is a subjective and quantitative exercise. In any case, no perfect model exists [42–46]. As a result, participants in financial markets are free to choose whichever probability model they calibrate to market data [47–49].
The problem with economics-based models and those in mathematical finance literature is that many times the analysis is centred on a representative agent. In the case of risk and uncertainty, the choice of pricing a derivative contract reduces to choosing a correct equivalent martingale measure under which a derivative claim is replicable. For market-makers and dealers, the choice of models is vast. Each player has to make a choice and inevitably no two institutions will use the same models with the same parameters. In this case, it is remarkable that the market will aggregate the diverse beliefs to arrive at a consensus smile. At the microscopic level, though, the dealers are observing one another’s updates. Hence, our model can be seen as a meta-opinion dynamics framework built upon the individual choices of the dealers.

### 2.5 Non-Bayesian financial markets

In financial markets, updating occurs at high frequency across geographical locations [50,51]. Agents move simultaneously: cancellations are the norm [52–54]. In practical terms, sequential Bayesian learning models do not seem appropriate [55,56]. Bayesian observational learning examples include [57–59]. These models are *sequential* in nature. They study herd behaviour. As time passes, a player in turn observes the actions of previous agents and receives a private signal. Each agent has a one-off decision when she updates her posterior probability and takes an action. In some instances, the *n*th agent may reach the truth as *n* → ∞.
In DeGroot learning, myopic updating occurs in each iteration. Agents in our set-up have fixed weights but update their responses until consensus is reached. Recently, there have been some experimental papers on the evidence of DeGroot updating [60,61]. Repeated averaging models are our base precisely because they capture the nature of interaction and learning in financial markets so compactly. Players can observe previous choices but not the payoffs of their competitors. A more in-depth discussion of learning in games would take us further away from our goal of studying the mathematical nature of interaction. The reader can consult [62,63] for a game-theoretic perspective.

## 3 Model description

In mathematical opinion dynamic models, agents take views of other agents into account before arriving at their own updated estimate. Agents can observe other agents’ previous signals.
DeGroot [64] was one of the early developers of such observational learning dynamics. While simple, these models allow us to examine convergence to consensus. In a sense, these types of models are called naive models, as agents can recall perfectly what the other players submitted in the previous round. See the survey papers [65–68].

### 3.1 Volatility basics

Agents have an initial opinion of the implied volatility, which they update after taking into account volatilities of other agents. A feedback mechanism aids the agents in arriving at the true volatility parameter.
At all times, the focus is on a static picture of the volatility smile. Within this static framework agents are updating their opinion of the true implied volatility. This updating occurs in a high-frequency sense. In an exchange setting, one can think of all bids and offers as visible to agents. The agents initially are unsure of the true value of the implied volatility, but by learning—and feedback—reach consensus on the true parameter. Our first attempt is a naive learning model common in social networks. Learning occurs between trading times. Therefore, our implicit assumption is that no transactions occur while traders are adjusting and learning each other’s quotes.
This rather peculiar feature is market practice. Trading happens at longer intervals than quote updating. This is as true for high-frequency trading of stocks as it is for options markets. Quotes and prices—or rather vols—are changing more frequently than actual transactions.
Each dollar value of an option corresponds to an implied volatility parameter *σ*(*K*, *T*) ∈ (0, 1) that depends on strike and expiry. Implied volatility is quoted in percentage terms.

#### Assumption 3.1.

We have three types of players: agents/traders, brokers and leaders. Brokers give feedback to the traders. The ability of agents to determine this feedback is their learning ability. Leaders are unknown and do not give feedback but their quotes are visible.

### 3.2 Naive opinion dynamics

*t*, the opinion of the
*i*-th agent is given by
*j*at time (*t*− 1) and
*a*
≥ 0 denotes the opinion weights for the
*ij**n*players with and
*a*
> 0 for all 1 ≤
*ii**i*≤
*n*. Define, then the opinion dynamics of the
*n*agents can be written in matrix form as follows:
*row-stochastic matrix*.

#### Definition 3.3 (consensus to a point).

The *n* agents (3.2) are said to reach consensus to a point if for any initial condition, lim
*t*→∞*X*
=
*t**c*
**1**, where
*n***1**
denotes the
*n**n*× 1 vector composed of only ones and. The constant
*c*is often referred to as the consensus value.

#### Proposition 3.4.

*Consider the opinion dynamics in equation* (3.2). *If A is aperiodic and irreducible, then for any initial condition**consensus to a point is reached. The consensus value c depends on both the matrix A and the initial condition X*1.

#### Remark 3.5.

Proposition 3.4 implies that if the row stochastic opinion matrix *A* is aperiodic and irreducible, then all the agents converge to some consensus value *c*. However, since *c* depends on the unknown initial opinion *X*1, the consensus value *c* is unknown and, in general, different from the true volatility *σ*(*K*, *T*). We wish to alleviate this and thus introduce two novel models.

## 4 Consensus (scalar agent dynamics)

In this section, we assume that the agents are able to learn how far off they are from the true volatility by informational channels in the marketplace. There are many avenues, platforms and private online chat rooms that provide quotes for option prices; some of these are stale and some are fresh. The agents’ learning ability determines the quality of the feedback from all these sources. In reality, options are not traded on one exchange or platform. There are multiple venues and, though there might be a dominant marketplace, the same instruments can be traded across different venues and locations. We aggregate all of this information in the form of feedback with learning ability. If agents are fast learners, they adjust their volatility estimates quickly.

### 4.1 Consensus with feedback

3.1). An early model developed by Mizuno
*et al.*[70] shares some similarities to ours. Traders use feedback from past behaviour. Our model is a discrete autoregressive process but the focus is on learning in high-frequency time [71]. Furthermore, our model formalizes this in a more social and dynamical set-up. In particular, we feed back the difference between the agents’ opinion and the true volatility
*σ*(*K*,
*T*) scaled by a
*learning coefficient ε*
∈ (0, 1). We assume that
*i**σ*(*K*,
*T*) is invariant, i.e. for some fixed, for some fixed strike
*K*and maturity
*M*. Then the new model is written as follows:

#### Proof.

*X*
of the difference equation (*t*4.2) is given by
*i*,
*ε*
<
*i**a*. It follows that, where
*ii**I*
denotes the identity matrix of dimension
*n**n*, and, see [72]. As the matrix
*A*is row stochastic, (*I*−
*A*)
**1**
=
*n***0**, where
*n***0**
denotes the
*n**n*× 1 vector composed of only zeros. Hence, we can write, and consequently. It follows that

#### Corollary 4.2.

*Consensus to**is reached exponentially with convergence rate*, *i.e.*, *i* ∈ {1, …, *n*}, *where**denotes the matrix norm induced by the vector infinity norm*.

#### Proof.. Then, from (*n*4.2), the following is satisfied:

*A*−
*I*)
*n***1**
= 0, because
*n**A*is a stochastic matrix. The solution
*E*
of the above difference equation is given by, where denotes the initial error. Let,
*t**i*∈ {1, …,
*n*}, where. Note that exponential convergence of implies exponential convergence of
*E*
itself. With the solution, the following can be written:
*t*72]. The inequality implies exponential convergence if. Because
*A*=
*a*
and, we can compute as,
*ij**i*∈ {1, …,
*n*}. The matrix
*A*is stochastic, which implies
*a*
≥ 0 and. Therefore, under the conditions of theorem 4.1 (i.e.
*ij**ε*
∈ (0,
*i**a*)), and hence exponential convergence of the consensus error
*ii**E*
can be deduced with rate given by. ▪
*t*### 4.2 Random case
Under suitable random conditions for the trust matrix *A* and, we can still have consensus. In this case, the learning rates and weights are independently and identically distributed from each iteration. However, we need a condition to ensure convergence, namely that on average the learning rates are less than the self-belief condition. Since this is only in expectation, a probabilistic statement, there is some leeway on the learning rates being strictly less than self-belief *a* ii at time
*t*.

#### Theorem 4.3.

*Consider the updating rule*
*where A*
*t**and*
*are independent and identically distributed (iid). Furthermore, suppose*
*then consensus to*
*is reached, i.e.*.

#### Proof.

*Y*
→ 0. To this end, iterating the above recursion gives us
*t*Note we do not require the stronger condition that for all *t*. Unlike the deterministic case, the random case allows considerable flexibility. Neither self-belief *a* ii > 0 nor positive learning
*ε*
is required for all times. However, there must be some interaction and learning for beliefs to converge. As matrix products do not commute, if we were to follow the full expansion of the recursion in any of the dynamics, the result would be long, unwieldy matrix products. Random matrix products and dynamics are an active area of research not only in mathematics but also in physics and control theory [*i*73–78]. While the random case is certainly interesting, in this article our focus is on the first steps of modelling interaction and learning dynamics.

### 4.3 Consensus with an unknown leader

One criticism of model (4.2) is that feedback, even if it is not perfect, has to be learned. In practice, there might not be a helpful mechanism that provides feedback. An alternative is to have an unknown leader embedded in the set of traders. The agents are unsure who the leader is but by taking averages of other traders, they all arrive at the opinion of the leader. In Markov chain theory, such behaviour is called an absorbing state. The leader guides the system to the true value. We assume that the *identity* of the leader is unknown to all agents.
*a*
1= 0,
*i**i*∈ {2, …,
*n*}, and
*a*
11= 1. Then in this configuration, the opinion dynamics is given by
*a*
≥ 0,,
*ij**a*
> 0 for all 1 ≤
*ii**i*≤
*n*, and for at least one
*i*≥ 2,.

#### Proof.

**0**denotes the zero vector of appropriate dimensions and as defined in (4.5). By construction,; hence, the consensus error
*e*
satisfies the following difference equation
*t**e*
is then given by.
*t*Because for at least one *i*, and is substochastic and irreducible, the spectral radius, see lemma 6.28 in [69]; it follows that. Therefore, lim *t*→∞*e* t =
**0**and the assertion follows. ▪

#### Corollary 4.5.

*Let**denote some matrix norm such that* (*such a norm always exists because**under the conditions of theorem 4.4). Then consensus to**is reached exponentially with the convergence rate given by*, *i.e.*, *for i* ∈ {1, …, *n*} *and some positive constant*.

#### Proof.

See lemma 5.6.10 in [72] on how to construct such a. Now consider the consensus error *e* t defined in the proof of theorem 4.4, which evolves according to the difference equation (4.6). It follows that, where
*e*
1denotes the initial consensus error. Under the assumptions of theorem 4.4,. By lemma 5.6.10 in [72], implies that there exists some matrix norm, say, such that. We restate the error with norms and obtain. Because all norms are equivalent in finite dimensional vector spaces (see ch. 5 in [72]), for some positive constant. As, the norm of the consensus error converges to zero exponentially with rate. ▪

## 5 Consensus (vectored agent dynamics)

In this section, we suppose that agents have beliefs over a range of strikes. Thus, each agent’s opinion of the volatility curve is a vector with each entry corresponding to a particular strike. Typically, in markets, options are quoted for At-The-Money (ATM) *K* = *S*0 and for two further strikes left of and right of the ATM level. Here, we examine the case of *k* strikes and *n* agents, i.e. each agent *i* now has *k* quotes for *k* different moneyness levels. In this configuration, the true volatility is. See figure 1*b*.

### 5.1 Consensus with feedback

*vector*for the next period. At time
*t*, the opinion of the
*i*-th agent is given by
*ε*
∈ (0, 1) denotes the
*i**learning coefficient*of agent
*i*, is the opinion of agent
*j*at time (*t*− 1), and
*a*
≥ 0 denotes the opinion weights for the
*ij**n*agents with and
*a*
> 0 for all 1 ≤
*ii**i*≤
*n*. In this case, the stacked vector of opinions is,. The opinion dynamics of the
*n*agents can then be written in matrix form as follows:
*row-stochastic matrix*,, and ⊗ denotes a Kronecker product. We have the following result.

#### Proof.

*e*
=
*t*−1**0**implies that consensus to is reached. Given the opinion dynamics in (5.2), the evolution of the error
*e*
satisfies the following difference equation:
*t*−1*A*is stochastic, (*A*−
*I*)
*n***1**
=
*n***0**. Then the error dynamics simplifies to
*n**e*
of (*t*5.3) is given by. By properties of the Kronecker product and Gershgorin’s circle theorem, the spectral radius for
*ε*
∈ (0,
*i**a*). It follows that, see [*ii*72]. Therefore, lim
*t*→∞*e*
=
*t***0**
and the assertion follows. ▪
*kn*#### Corollary 5.2.
*Consensus to**is reached exponentially with the convergence rate given by*, *i.e*..
The proof of the above result is very similar to previous corollaries and is omitted.

### 5.2 Consensus with an unknown leader

*A*. Again, without loss of generality, we assume that the first agent (with corresponding opinion) is the leader,,
*a*
1= 0,
*i**i*∈ {2, …,
*n*}, and
*a*
11= 1. Then in this configuration, the opinion dynamics is given by
*a*
≥ 0,,
*ij**a*
> 0 for all 1 ≤
*ii**i*≤
*n*, and for at least one
*i*≥ 2,.

#### Theorem 5.3.

The proof of theorem 5.3 follows the same line of reasoning as the proof of theorem 4.4 and it is omitted here.

#### Corollary 5.4.

*Let**denote some matrix norm such that*. *Then consensus to**is reached exponentially with convergence rate*, *i.e*., *for some positive constant*.

## 6 Numerical simulations

4.2) with 10 agents (*n*= 10), and initial condition
79,
80]. Option market-makers are usually investment banks and big trading houses. In this sense, the number of players is not large and thus the models developed always have a finite number of agents,
*N*= 10.
Figure 2depicts the obtained simulation results for different values of the learning parameters
*ε*,
*i**i*= 1, …, 10. Specifically,
figure 2
*a*shows results without learning, i.e,
*ε*
= 0 (here there is no consensus to),
*i*figure 2
*b*depicts the results for
*ε*
= 0.9
*i**a*. As stated in theorem 4.1, consensus to is reached.
*ii*Figure 2
*c*shows results for
*ε*
= 0.9
*i**a*
+ 0.94
*ii**b*
with
*i**b*
4= 1 and
*b*
= 0 otherwise,
*i**i*= 1, …, 10. Note that, in this case, the value of
*ε*
4violates the condition of theorem 4.1 (i.e.) and, as expected, consensus is not reached. Next, consider the opinion dynamics with a leader (4.5) with
*n*= 10 and initial condition
*A*by (1, 0, …, 0). The corresponding matrix (defined in
4.5) is substochastic and irreducible, and,
*j*= 1, …, 10. Hence, all the conditions of theorem 4.4 are satisfied and consensus to is reached.
Figure 2
*d*shows the corresponding simulation results. Finally,
figure 3shows the evolution of the vectored opinion dynamics (5.2) with
*n*= 10 and
*k*= 3 (i.e. 10 three-dimensional agents), matrix
*A*as in the case with feedback, (vectored) volatility, learning parameters
*ε*
= 0.9
*i**a*
for
*ii**a*
as in
*ii**A*, and initial condition
**1**
⊗
*k**X*
1with
*X*
1as in the first experiment above.

## 7 Arbitrage bounds

We have taken the true volatility parameter as exogenous to our models. Our only requirement is that there is no static arbitrage, by which we mean that all the quotes in volatility which translate to option prices are such that one cannot trade in the different strikes to create a profit. Checking whether a volatility surface is indeed arbitrage-free is non-trivial, nevertheless some sufficient conditions are well known [81–83]. As long as the volatility surface satisfies them our analysis implies global stability towards an arbitrage-free smile.
*K*, to ensure no static arbitrage. We assume that the
*σ*(*K*) translates into unique call option dollar prices. This follows from the strictly positive first derivative of the option price formula with respect to
*σ*. We require two conditions:
- —
**Condition 1: (Call Spread)**For 0 <*K*1≤*K*2, we have - —
**Condition 2: (Butterfly Spread)**For 0 <*K*1<*K*2<*K*3,
*et al.*[84] examine the case of checking static arbitrage conditions, using machine learning techniques; moreover, their notion of quotes being arbitrage-free is extended to exclude calendar spread arbitrage across different maturities. We highlight the conditions needed for a single slice of the volatility surface as
*T*is fixed in our environment. How arbitrage-free curve volatility conditions are developed is not an easy task: see the extended accounts in [32,
84–88].

## 8 Discussion

### 8.1 Future work

Social learning is an active area of research in many different fields. By combining aspects of social learning models with dynamical systems, we were able to develop insightful analysis for the volatility smile. This can be extended further. There are several immediate possibilities. Can the number of strikes be infinite? We restricted the models to a finite number of strikes: fixed *k*. In practical terms, at any given time, there are usually two strikes below and two strikes above the ATM level that are liquid. This means the corresponding quotes are visible or updated for five strikes. One way to circumvent this is to consider arbitrage-free volatility curves. But again, we are faced with the observational nature of our framework. A trader only observes a fixed number of strikes of his competitors. The issue of how to introduce heterogeneity in the volatility curves, which themselves emanate from specific pricing models, remains open.
The number of agents can also be infinite. Perhaps a propagation of chaos type of result could shed some light on how an individual trader interacts with the mean-field limit [89–91]. In this case, we lose the heterogeneity of beliefs and the behaviour we are trying to study would have a different implication. Moreover, considerable technical machinery is required [92,93]. We could study the pure limiting behaviour as *t*, *n* → ∞. In our current framework, this would have to be balanced with whether an individual can observe an infinite number of competitors. While the technical subtleties are not insurmountable, the modelling issues are more subjective.
The technical issues in random matrix products, briefly discussed in this paper, assure us that much more work needs to be done on the modelling and mathematical front. For example, the matrices *A* and can be dependent with correlation decreasing in time. Work in this direction has been addressed by Popescu & Vaidya [94].

### 8.2 Connection

Recently, there has been some rather interesting work at the intersection of computer science and option pricing. Demarzo *et al.* [95] showed how to use efficient online trading algorithms to price the current value of financial instruments, deriving both upper and lower bounds using online trading algorithms. Moreover, Abernethy *et al.* [96,97] developed a BS price as sequential two-player zero-sum game. While these papers made an excellent start to bridge the gap between two different academic communities—mainly mathematical finance and theoretical computer science—they do not address the reality of volatility smiles and trading. Our contribution can be viewed as making these connections more concrete. The smile itself is a conundrum and there have even been articles questioning whether it can be solved [98]. The traditional way from the ground up is to develop a stochastic process for the volatility and asset price, possibly introducing jumps or more diffusions through uncertainty [99,100]. Such models have been successfully developed, but the time is ripe to incorporate multi-agent models with arbitrage-free curves.
Introducing learning agents in stochastic differential equation models [101], such as the BS model, is an exciting proposition. Moreover, opinion dynamics as a subject on its own has been studied quite extensively. Recent references that present an expansive discussion in computer science are [8,102]. Econophysics is the right community to develop new models. After all, there is no attachment to utilities of players or stochastic volatility models so entrenched in the mathematical finance community. Free from these shackles, researchers can use a range of tools and techniques to build more sophisticated models. Moreover, there is no restriction or debate on continuous or discrete time. While our framework is discrete, continuous time could perhaps show a way forward to incorporate models from mathematical finance and financial economics [103–105]. Jarrow [106] makes the case for continuous time, arguing that today’s financial markets trade and update at high frequency.
In this paper, we introduce models of learning agents in the context of option trading. A key open question in this setting is how the market comes to a consensus about market volatility, which is reflected in derivative pricing through the BS formula. The framework we have established allows us to explore other areas. Thus far, we took the smile as an exogenous object, proving convergence to equilibrium beliefs. A natural step forward would be to look at the beliefs as probability measures, where each measure corresponds to a different option pricing model. Our learning models focus on interaction between agents. Actually, agents can be interpreted as algorithms. Each algorithm corresponds to a particular belief of a pricing model. Until now, the replication paradigm has led to very sophisticated models. The future may belong to deep hedging arguments [107]. Still, whether we consider models or algorithms, interaction will always be a topic of interest.

## Footnotes

Using the BS formula with a particular implied volatility, traders obtain a dollar value for the price.
[http://creativecommons.org/licenses/by/4.0/](http://creativecommons.org/licenses/by/4.0/), which permits unrestricted use, provided the original author and source are credited.

## Figures

- Figure
- Figure
- Figure

## References (108 total, showing 108)

- Schinckus C. Methodological comment on Econophysics review I and II: statistical econophysics and agent-based econophysics. Quant. Finance. 2012
- Chakraborti A, Toke IM, Patriarca M, Abergel F. Econophysics review: I. Empirical facts. Quant. Finance. 2011
- Kirman A. Reflections on interaction and markets. Quant. Finance. 2002
- Föllmer H, Horst U, Kirman A. Equilibria in financial markets with heterogeneous agents: a probabilistic perspective. J. Math. Econ.. 2005
- Chakraborti A, Toke IM, Patriarca M, Abergel F. Econophysics review: II. Agent-based models. Quant. Finance. 2011
- Papadimitriou C, Piliouras G. Game dynamics as the meaning of a game. SIGEcom Exchanges. 2018
- Piliouras G, Nieto-Granda C, Christensen HI, Shamma JS. 2014
- Mai T, Panageas I, Vazirani VV. 2017
- Bacoyannis V, Glukhov V, Jin T, Kochems J, Song DR. 2018
- Ganesh S, Vadori N, Xu M, Zheng H, Reddy P, Veloso M. 2019
- Wei H, Wang Y, Mangu L, Decker K. 2019
- Malamud S, Rostek M. Decentralized exchange. Am. Econ. Rev.. 2017
- Duffie D. Dark markets: asset pricing and information transmission in over-the-counter markets. 2011
- Chriss N. Black Scholes and beyond: option pricing models. 1996
- Otto M. Finite arbitrage times and the volatility smile?. Physica A. 2001
- Kakushadze Z. Volatility smile as relativistic effect. Physica A. 2017
- Derman E, Miller MB. The volatility smile. 2016
- Sornette D. Physics and financial economics (1776–2014): puzzles, Ising and agent-based models. Rep. Prog. Phys.. 2014
- Vagnani G. The Black–Scholes model as a determinant of the implied volatility smile: a simulation study. J. Econ. Behav. Organ.. 2009
- Liu YF, Zhang W, Xu HC. Collective behavior and options volatility smile: an agent-based explanation. Econ. Modell.. 2014
- Li T. Investors’ heterogeneity and implied volatility smiles. Manage. Sci.. 2013
- Platen E, Schweizer M. On feedback effects from hedging derivatives. Math. Finance. 1998
- Challet D. Regrets, learning and wisdom. Eur. Phys. J. Spec. Top.. 2016
- Iori G, Porter J. 2012
- Sinha S, Chatterjee A, Chakraborti A, Chakrabarti BK. Econophysics: an introduction. 2010
- Stanley HE. Anomalous fluctuations in the dynamics of complex systems: from DNA and physiology to econophysics. Physica-Section A. 1996
- Schinckus C. Ising model, Econophysics and analogies. Physica A. 2018
- Castellano C, Fortunato S, Loreto V. Statistical physics of social dynamics. Rev. Mod. Phys.. 2009
- LeBaron B. A builder’s guide to agent-based financial markets. Quant. Finance. 2001
- Farmer JD, Foley D. The economy needs agent-based modelling. Nature. 2009
- Samanidou E, Zschischang E, Stauffer D, Lux T. Agent-based models of financial markets. Rep. Prog. Phys.. 2007
- Lee RW. 2005
- Jacquier A, Shi F. The randomized Heston model. SIAM J. Finance Math.. 2019
- Gatheral J, Jaisson T, Rosenbaum M. Volatility is rough. Quant. Finance. 2018
- Ellsberg D. Risk, ambiguity, and the Savage axioms. Q. J. Econ.. 1961
- Knight FH. Risk, uncertainty and profit. 2012
- Schinckus C. Economic uncertainty and econophysics. Physica A. 2009
- Assa H, Gospodinov N. Market consistent valuations with financial imperfection. Decis. Econ. Finance. 2018
- Cousot L. Necessary and sufficient conditions for no static arbitrage among European calls. 2004
- Laurent JP, Leisen DP. 2001
- Buehler H. Expensive martingales. Quant. Finance. 2006
- Duembgen M, Rogers L. Estimate nothing. Quant. Finance. 2014
- Khrennikova P, Patra S. Asset trading under non-classical ambiguity and heterogeneous beliefs. Physica A. 2019
- Mykland PA. Financial options and statistical prediction intervals. Ann. Stat.. 2003
- Cheridito P, Kupper M, Tangpi L. Duality formulas for robust pricing and hedging in discrete time. SIAM J. Finance Math.. 2017
- Acciaio B, Beiglböck M, Penkner F, Schachermayer W. A model-free version of the fundamental theorem of asset pricing and the super-replication theorem. Math. Finance. 2016
- Davis MH. 2016
- Cont R. Model uncertainty and its impact on the pricing of derivative instruments. Math. Finance. 2006
- Burzoni M, Frittelli M, Maggis M. Universal arbitrage aggregator in discrete-time markets under uncertainty. Finance Stoch.. 2016
- Wissner-Gross AD, Freer CE. Relativistic statistical arbitrage. Phys. Rev. E. 2010
- Buchanan M. Physics in finance: trading at the speed of light. Nature. 2015
- Gu GF, Xiong X, Ren F, Zhou WX, Zhang W. The position profiles of order cancellations in an emerging stock market. J. Stat. Mech: Theory Exp.. 2013
- Yoshimura Y, Okuda H, Chen Y. A mathematical formulation of order cancellation for the agent-based modelling of financial markets. Physica A. 2020
- Eisler Z, Bouchaud JP, Kockelkoren J. The price impact of order book events: market orders, limit orders and cancellations. Quant. Finance. 2012
- Hkazla J, Jadbabaie A, Mossel E, Rahimian MA. 2019
- Mossel E, Sly A, Tamuz O. Asymptotic learning on Bayesian social networks. Probab. Theory Relat. Fields. 2014
- Banerjee AV. A simple model of herd behavior. Q. J. Econ.. 1992
- Bikhchandani S, Hirshleifer D, Welch I. A theory of fads, fashion, custom, and cultural change as informational cascades. J. Pol. Econ.. 1992
- Smith L, Sørensen P. Pathological outcomes of observational learning. Econometrica. 2000
- Chandrasekhar AG, Larreguy H, Xandri JP. Testing models of social learning on networks: evidence from two experiments. Econometrica. 2019
- Becker J, Brackbill D, Centola D. Network dynamics of social influence in the wisdom of crowds. Proc. Natl Acad. Sci. USA. 2017
- Fudenberg D, Levine DK. The theory of learning in games. 1998
- Kalai E, Lehrer E. Weak and strong merging of opinions. J. Math. Econ.. 1994
- DeGroot MH. Reaching a consensus. J. Am. Stat. Assoc.. 1974
- Masuda N, Porter MA, Lambiotte R. Random walks and diffusion on networks. Phys. Rep.. 2017
- Acemoglu D, Ozdaglar A. Opinion dynamics and learning in social networks. Dyn. Games Appl.. 2011
- Golub B, Sadler E. 2016
- Noorazar H. Recent advances in opinion propagation dynamics: a 2020 Survey. Eur. Phys. J. Plus. 2020
- Salinelli E, Tomarelli F. 2014
- Mizuno T, Nakano T, Takayasu M, Takayasu H. Traders’ strategy with price feedbacks in financial market. Physica A. 2004
- Mizuno T, Kurihara S, Takayasu M, Takayasu H. Analysis of high-resolution foreign exchange data of USD-JPY for 13 years. Physica A. 2003
- Horn RA, Johnson CR. Matrix analysis. 2012
- Diaconis P, Freedman D. Iterated random functions. SIAM Rev.. 1999
- Crisanti A, Paladin G, Vulpiani A. Products of random matrices: in statistical physics. 2012
- Bruneau L, Joye A, Merkli M. 2010
- Garnerone S, de Oliveira TR, Zanardi P. Typicality in random matrix product states. Phys. Rev. A. 2010
- Tahbaz-Salehi A, Jadbabaie A. A necessary and sufficient condition for consensus over random networks. IEEE Trans. Autom. Control. 2008
- Askarzadeh Z, Fu R, Halder A, Chen Y, Georgiou TT. Stability theory of stochastic models in opinion dynamics. IEEE Trans. Autom. Control. 2019
- Guéant O. The financial mathematics of market liquidity: from optimal execution to market making. 2016
- Bouchaud JP, Bonart J, Donier J, Gould M. Trades, quotes and prices: financial markets under the microscope. 2018
- Carr P, Madan DB. A note on sufficient conditions for no arbitrage. Finance Res. Lett.. 2005
- Gatheral J, Jacquier A. Arbitrage-free SVI volatility surfaces. Quant. Finance. 2014
- Tehranchi MR. Uniform bounds for Black–Scholes implied volatility. SIAM J. Finance Math.. 2016
- Assa H, Pouralizadeh M, Badamchizadeh A. Sound deposit insurance pricing using a machine learning approach. Risks. 2019
- Roper M. 2010
- Rogers L, Tehranchi M. Can the implied volatility surface move by parallel shifts?. Finance Stoch.. 2010
- Delbaen F, Schachermayer W. The mathematics of arbitrage. 2006
- Ellersgaard S, Jönsson M, Poulsen R. The fundamental theorem of derivative trading-exposition, extensions and experiments. Quant. Finance. 2017
- Budhiraja A, Pal Majumder A. Long time results for a weakly interacting particle system in discrete time. Stoch. Anal. Appl.. 2015
- Carmona R, Delarue F. Probabilistic theory of mean field games with applications. I. 2018
- Boers N, Pickl P. On mean field limits for dynamical systems. J. Stat. Phys.. 2016
- Kolarijani MAS, Proskurnikov AV, Esfahani PM. Macroscopic noisy bounded confidence models with distributed radical opinions. IEEE Trans. Autom. Control
- Jabin PE, Motsch S. Clustering and asymptotic behavior in opinion formation. J. Differ. Equ.. 2014
- Popescu I, Vaidya T. 2019
- DeMarzo P, Kremer I, Mansour Y. 2006
- Abernethy J, Frongillo RM, Wibisono A. 2012
- Abernethy J, Bartlett PL, Frongillo R, Wibisono A. 2013
- Ayache E, Henrotte P, Nassar S, Wang X. 2004
- Kamal M, Gatheral J. 2010
- Kyprianou A, Schoutens W, Wilmott P. Exotic option pricing and advanced Lévy models. 2006
- Schweizer M, Wissel J. Arbitrage-free market models for option prices: the multi-strike case. Finance Stoch.. 2008
- Mossel E, Tamuz O. Opinion exchange dynamics. Probab. Surv.. 2017
- Nadtochiy S, Obłój J. Robust trading of implied skew. Int. J. Theor. Appl. Finance. 2017
- Davis MH, Hobson DG. The range of traded option prices. Math. Finance. 2007
- Shafer G, Vovk V. Game-theoretic foundations for probability and finance. 2019
- Jarrow RA. Continuous-time asset pricing theory. 2018
- Buehler H, Gonon L, Teichmann J, Wood B. Deep hedging. Quant. Finance. 2019
- Vaidya T, Murguia C, Piliouras G. Dryad Digital Repository. 2020
