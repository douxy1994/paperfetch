---
title: "10.1098/rsif.2019.0334"
authors: "Miller-Dickson, Miles D., Meszaros, Victor A., Almagro-Moreno, Salvador, Brandon Ogbunugafor, C."
journal: "Journal of The Royal Society Interface"
doi: "10.1098/rsif.2019.0334"
published: "2019/09/01"
source: "royalsocietypublishing_html"
has_fulltext: true
content_kind: "fulltext"
has_abstract: true
token_estimate: 6802
---

# 10.1098/rsif.2019.0334

## Abstract

The hepatitis C virus (HCV) epidemic often occurs through the persistence of injection drug use. Mathematical models have been useful in understanding various aspects of the HCV epidemic, and especially, the importance of new treatment measures. Until now, however, few models have attempted to understand HCV in terms of an interaction between the various actors in an HCV outbreak—hosts, viruses and the needle injection equipment. In this study, we apply perspectives from the ecology of infectious diseases to model the transmission of HCV among a population of injection drug users. The products of our model suggest that modelling HCV as an indirectly transmitted infection—where the injection equipment serves as an environmental reservoir for infection—facilitates a more nuanced understanding of disease dynamics, by animating the underappreciated actors and interactions that frame disease. This lens may allow us to understand how certain public health interventions (e.g. needle exchange programmes) influence HCV epidemics. Lastly, we argue that this model is of particular importance in the light of the modern opioid epidemic, which has already been associated with outbreaks of viral diseases.

## 1 Introduction

While the ecology of infectious disease is a rich field with decades worth of empirical evidence and theory, there are aspects that remain relatively under-explored. One example is the importance of the free-living survival stage of certain pathogens, where diseases are transmitted indirectly between hosts through an environmental reservoir intermediate. These include infections transmitted indirectly between hosts via a surface or reservoir intermediate—often abiotic—where the pathogen lives freely and independently of a host [1–18], sometimes described as ‘sit and wait’ infections [19]. Other studies have focused on systems where pathogens are growing in the environment [9], or have explored indirectly transmitted infections in theoretical terms [12,15]. While frameworks already exist for studying indirect environmental transmission, most are engineered with constraints that render their application necessarily narrow [6], limiting their relevance for a wider number of indirectly transmitted infections.
One class of diseases where the indirect transmission paradigm has been scarcely applied are those spread through injection drug use in urban settings, such as the human immunodeficiency virus (HIV) and hepatitis C virus (HCV). HIV has been the object of many important mathematical models [20,21], some of which have implemented injection drug use effectively, even focusing on the specific dynamics of injection equipment [22–25]. HCV has also been studied using modelling methods, many focusing on treatment [26–28] and others on the particulars of transmission in injection drug-user communities [29–35]. Importantly, none of these existing dynamical models consider the peculiar ecology of HCV transmission, where transmission events occur through an environmental reservoir (injection equipment) that resembles a disease vector [36,37]. Unlike an insect vector, however, injection equipment is not an organism and is more realistically considered an abiotic reservoir for infection, similar to the role that the water supply serves in an outbreak of cholera or other waterborne diseases [38]. As HCV continues to pose a serious public health challenge in many communities, there is a need to understand how the dynamics of injection equipment influence HCV transmission. This is especially important for informing the utility of harm reduction programmes, such as needle exchange, which have been effective in decreasing transmission of HIV and HCV [39,40]. Lastly, but perhaps most importantly, the urgency for understanding these dynamics has increased dramatically in recent years with the growth of the modern opioid epidemic, much of it involving injection drug use [41,42]. The lack of models of HCV that specifically consider injection equipment, and increased social urgency related to the modern opioid epidemic implore more adaptable mathematical models of injection-drug use that could facilitate a better understanding of and predictions for the trajectory of modern HCV infections.
In this study, we model HCV as an indirectly (or environmentally) transmitted infection, where the drug paraphernalia serves as the environmental reservoir. As HCV epidemics are partly defined by injection drug users and injection drug equipment, we argue that this indirectly transmitted lens captures aspects that prior models have not. In §[2](#s2), we introduce a theoretical iteration of an indirectly transmitted infection using a standard epidemiological model imbued with an environmental reservoir compartment. We describe analytic equations of such a system, and derive the reproductive number (*R*0) using analytic methods. Then in §[3](#s3), we introduce the full HCV mathematical model, demonstrating how it allows one to examine several otherwise-overlooked features of disease dynamics. We pontificate on these results in light of the ecology of infectious diseases, and in terms of public health policies, especially as they relate to the modern opioid epidemic.

## 2 An elementary adapted SIR indirectly transmitted iteration

### 2.1 Description

While the emphasis of our examination will reside in how we analyse a HCV epidemic, for explanatory purposes we will begin by describing how an environmental reservoir modifies very basic concepts in a classic, purposefully prosaic susceptible–infected–recovered (SIR) mathematical model. We will explain the basic structure of a model of indirect transmission, after which the HCV-specific iteration will be discussed.
While there are several existing frameworks that can be used to describe infections spreading through an environmental reservoir, we have conveniently labelled ours the waterborne, abiotic and indirectly transmitted (W.A.I.T.) infection model. Many diseases can be modelled using this kind of approach, but this study applies it to HCV in a community of injection drug users, which has not been previously modelled in this manner.
*β*factor, or transmission coefficient.
Figure 1is a compartmental model that depicts this interaction, and adds two additional compartments, labelled with a
*W*(for W.A.I.T.), which influence the flow of hosts from the susceptible to infected compartments—indicated by the dashed lines in the figure.

### 2.2 The adapted SIR compartmental diagram

The *S*, *I* and *R* compartments represent the usual *susceptible*, *infected* and *recovered* populations of hosts, respectively. *W* u and
*W*
represent uninfected and infected populations of
*i**environmental*agents, respectively.
In traditional SIR models, the rate of new infection (arrow from the *S* compartment to the *I*) is generally proportional to the product of the susceptible and the infected populations, i.e. proportional to *SI*. In the W.A.I.T. framework, the environmental compartment plays a role analogous to the infected *host* compartment in driving the rate of infection. In this specific example, the *W* i compartment contributes to the rate of infection as a fraction,
*W*
/(*i**W*
+
*i**W*), which appears as a factor in the rate terms.
*u**S*and the infected (transmitting) environmental compartment
*W*, and interactions between infected individuals
*i**I*and the uninfected environmental compartment
*W*. The epidemic is sustained through infected hosts
*u**I*depositing pathogen into the environmental reservoir, creating new infections, which can then infect more susceptible hosts
*S*(in a process resembling a feedback loop). These dynamics can be captured by the set of dynamical equations and visualized with the diagram in
figure 1:
Equations (2.1)–(2.5) define an extension of the prosaic SIR model. *π* S is the birthrate of new susceptible hosts and
*μ*is the fractional death rate of hosts. In this context,
*β*represents the
*strength*of the interaction between the susceptible hosts
*S*and the environmental reservoir. This will generally be proportional to the rate of contact between the two. Similarly,
*α*characterizes the strength of interaction between infected hosts
*I*and the environmental reservoir, and is also generally proportional to the contact rate between the two.
*α*and
*β*, while both generally proportional to the contact rate between environmental agents and living hosts, are distinguished by factors that indicate the probabilities of spreading the infection either from host to environment, as in the case of
*α*, or from the environment to host, as in the case of
*β*. Note that
*α*and
*β*could be replaced with the same parameter in settings where the infection is guaranteed to spread at any encounter with an infected host or environmental agent.
*ν*represents the fractional recovery rate,
*π*
is the birthrate of new uninfected environmental agents and
*W**k*is the fractional death or discard rate of environmental agents. Note that the discard rate
*k*(which includes any force that removes environmental agents from the system) can be split into two discard rates, one for the infected compartment, and one for the uninfected compartment (we do, in fact make this distinction in the full HCV model). For simplicity, we will tend to set the discard rates of these two compartments equal, where there are two parameters, as we have no current mathematical grounds to distinguish them.
Also note that this model resembles vector-borne transmission models such as those used to study malaria [37]. In fact, prior studies have explored the utility of applying vector-borne transmission models to the spread of infection with needles as a proxy for vectors—although, only in the context of HIV [36]. In this paper, however, we wish to emphasize peculiarities of the spread of HCV and, further, to elaborate some features of the *R*0 expression in the context of these *shared* dynamical settings—between hosts and agents—which we believe have not been rigorously addressed in the existing literature.

### 2.3 W.A.I.T. framework influences the basic reproductive number in a standard SIR model

*R*
0in this model compares to its SIR counterpart. While
*R*
0can have different theoretical formulations, we rely on definitions as provided by Jones [43] and Diekmann
*et al*. [44]. In a density-dependent SIR model with constant birth of susceptible hosts
*π*
and death rate proportional to the host population −
*S**μS*, the
*R*
0value is given by
*SIR*equations used, e.g. frequency-dependent, constant population, etc. In this equation,
*β*is the traditional transmission coefficient. It represents the coupling strength between infected and uninfected hosts, two non-environmental agents. Whereas, in the W.A.I.T. model, what is analogous to
*β*is a pair of parameters
*α*and
*β*, which govern the interaction strengths between hosts and the environment.
*π*,
*S**μ*and
*ν*have the same interpretation as in the W.A.I.T. model.
*R*
0takes the form
There are some notable differences in the *R*0 formulae of the SIR and W.A.I.T. models: the square root in the W.A.I.T. version arises as a consequence of implementing two infected agents (*I* and *W* i) into the model, as opposed to just one in the SIR case. Next, one notices that the
*β*factor in the SIR formula is augmented by the additional factor
*α*in the W.A.I.T. formula, representing a kind of shared dependence between the couplings controlling the
*I*-interaction (*α*) and the
*S*-interaction (*β*) with the environment. Analogously, what was the responsibility of
*π*
in the SIR formula now presents itself as a shared dependence,
*S**π*
/
*S**π*, the ratio of the birthrate of susceptible hosts to that of uninfected environmental agents. In this case, the two appear as a ratio under the square root, as opposed to a product in the
*W**αβ*case, indicating that whereas
*α*and
*β*contribute to
*R*
0in the same way,
*π*
and
*S**π*
contribute in opposite ways: when
*W**π*
is increased,
*S**R*
0increases, but when
*π*
is increased,
*W**R*
0decreases.
*R*
0values. Namely, there is the reproductive ratio associated with the number of secondary host infections caused by a single infected environmental agent, and there is the reproductive ratio associated with the number of secondary environmental agent infections caused by a single infected host. We denote the former by and the latter by (*H*for hosts and
*W*for the W.A.I.T. compartment). From equations (2.1)–(2.5), one can see that the rate of new host infection due to infected environmental agents
*W*
is given by
*i**βSW*
/(*i**W*
+
*i**W*). Near the disease-free equilibrium (DFE),
*u**S*≈
*π*
/
*S**μ*and
*W*
/(*i**W*
+
*i**W*) ≈
*u**kW*
/
*i**π*
(near the DFE,
*W**W*
≪
*i**W*), which implies that near the DFE, the rate of new host infection per
*u**infected*environmental agent is ≈
*βπ*
*S**k*/(*μπ*). The average amount of time an infected environmental agent remains infected is 1/
*W**k*, i.e. the reciprocal of the exit rate of the infected state. Thus, the number of new host infections caused by an infected environmental agent in the time that the agent is infected, and while the system is near the DFE, is given by
*βπ*
*S**k*/(*μπ*) × 1/
*W**k*=
*βπ*
/(*S**μπ*). That is
*W**αIW*
/(*u**W*
+
*i**W*). Near the DFE, this rate, per infected host, is ≈
*u**α*(since
*W*
/(*u**W*
+
*i**W*) ≈ 1), and the average time that an infected host remains infected is given by 1/(*u**μ*+
*ν*), the reciprocal of the exit rate of the infected state. Thus, the number of new environmental agent infections caused by an infected host in the time that the host is infected (near the DFE) is given by
From this perspective, one can observe how a characteristic feature of the epidemic is modified by *indirect* transmission.

## 3 The hepatitis C virus model

### 3.1 Description

Our HCV model represents an adaptation of the SIR W.A.I.T. model outlined in §[2](#s2), but engineered around the particulars of HCV. Our model simulates a population of approximately 170 000 individuals—based on estimates of the size of the people who inject drugs (PWID) community in New York City [45]—where infected injection drug users may migrate into the population. In this model, injection paraphernalia serve as the environmental reservoir for HCV and the sharing of this equipment will constitute the means of transmitting new infections. While the entirety of injection paraphernalia might contain other components, many parameters in this model are based on the use of needle and syringe as the instrument of injection and sharing. Consequently, we use the term ‘needle’ in this paper as a synecdoche for the entire injection apparatus. It is also important to note that HCV can be transmitted sexually [46], but in this study we restrict our attention to transmission through infected needles. This main text focuses on the main structure and dynamical properties of the model. Further model details and discussion can be found in the electronic supplementary material, appendix.

### 3.2 HCV W.A.I.T. model: compartmental diagram

We model the dynamics of needle populations and injection drug users through a series of five ordinary differential equations. The compartments labelled *S*, *I* E,
*I*,
*L**N*
and
*u**N*
represent the populations of susceptible individuals, early-stage infected individuals (acute HCV infection), late-stage-infected individuals (chronic HCV infection), uninfected needles and infected needles, respectively (*i*figure 2). Here, we refer to all needles in circulation within the entire PWID community. This model is defined by several features:
- —
The susceptible compartment refers to individuals who are injecting drugs and who are sharing needles with other members in the PWID community.
- —
The needle population is divided into two compartments: infected and uninfected, and we model the dynamics of each compartment separately. This is analogous to the
*W*and*i**W*terms discussed in the preliminary model.*u* - —
New infections (of both hosts and needles) will depend on the
*fraction*of infected or uninfected needles in circulation. - —
Newly infected individuals enter the early stage compartment
*I*first before either spontaneously clearing the infection or moving into the late-stage compartment*E**I*, from which we assume no spontaneous clearance occurs—individuals may leave*L**I*either by treatment or death only, since cases of spontaneously clearing*L**chronic*HCV are rare. - —
There are various estimates for the ability of HCV to survive in needles [47,48]. We incorporate HCV free-living survival via the parameter*ε*, which quantifies the rate at which the virus decays on infected needles.

### 3.3 HCV W.A.I.T. model: analytic equations and parameters

The dynamics of the HCV transmission process are governed by equations (3.1)–(3.5). The population of individuals that are being treated and those who have recovered are not explicitly modelled in this iteration, as the dynamics of treatment and recovery are not central to the questions explored in this study. There are, however, several modelling studies of HCV that focus on treatment [26–28,49], and their effects are not ignored in the HCV W.A.I.T. model.
*τI*
and −
*L**τI*
and the susceptible ‘birth’ term
*E**π*.
*S**π*
is the birthrate of new members into the PWID community either via migration, first-time use or recovery
*S**from*treatment—not from spontaneous
*self-clearance*.
*ϕ*represents the daily fractional rate that acutely infected individuals (or
*early infected*
*I*) spontaneously clear the infection—i.e. without treatment.
*E**α*represents the
*per capita*injection rate, scaled by the fraction of injection events by infected users that render a needle infectious.
*β*represents the
*per capita*injection rate, scaled by the fraction of injection events with an infected needle that leave a susceptible host infectious.
*μ*is the combined fractional death and PWID cessation rate (individuals who leave the PWID community).
*ω*is the daily fractional rate that early stage infected individuals progress to the late stage of infection.
*τ*is the daily fractional rate that infected individuals go into treatment.
*π*
is the rate of introduction of uninfected needles into the PWID population.
*N**k*
is the daily fractional discard rate of uninfected needles.
*u**k*
is the daily fractional discard rate of infected needles. Lastly, is the daily fractional rate that infected needles clear the infection due to de-activation (or ‘death’) of virus populations on the needle. Parameter values and sources can be seen in
*i*table 1.
| label | value | units | description | sources |
|---|---|---|---|---|
πS | 47 ± 10 | person/day | birthrate of susceptibles (chosen to keep π/Nμ ≈ 170 000) | estimate |
ϕ | (4.7 ± 0.5) × 10−3 | %/day | daily fractional self-clearance rate | [πS | 47 ± 10 | person/day | birthrate of susceptibles (chosen to keep π/Nμ ≈ 170 000) | estimate |
ϕ | (4.7 ± 0.5) × 10−3 | %/day | daily fractional self-clearance rate | [|
α | 4 ± 3 | injection rate times infection of needle probability | [| |
β | 0.072 ± 0.05 | injection rate times infection of host rate | [| |
μ | (2.7 ± 0.5) × 10−4 | %/day | fractional rate of removal from PWID community due to cessation and death | [|
ω | 0.006 ± 0.005 | %/day | fractional transfer rate into late-stage infection | [|
τ | 0.011 ± 0.005 | %/day | fractional rate of entering treatment | [|
πN | (3.14 ± 0.01) × 104 | needles/day | birthrate of uninfected needles (chosen to keep π/Nk ≈ 220 000)u | [|
ku | 0.143 ± 0.005 | %/day | fractional discard rate of uninfected needles | estimate |
ki | 0.143 ± 0.005 | %/day | fractional discard rate of infected needles | estimate |
ɛ | 1.17 ± 0.05 | %/day | fractional decay rate of HCV infection in needles | [|

### 3.4 HCV W.A.I.T. model parameters influence *R*0

*R*
0. We directly measured the influence of parameters on
*R*
0by considering the
*partial rank correlation coefficient*(PRCC), discussed below. The value of
*R*
0was calculated using established methods [43,
44] and is outlined in the electronic supplementary material, appendix:
The left-most factor (under the square root) can be interpreted as the number of secondary infections of *needles* in the average time that a *host* is infected (near the DFE), and the right-most factor can be regarded as the number of secondary infections of *hosts* in the average time that a *needle* remains infected. Further discussion of this result can be found in the electronic supplementary material, appendix. As with traditional values of *R*0, we find that our value is consistent with the statement that sign(*R*0 − 1) = sign(*λ*), where *λ* is the maximal eigenvalue of the Jacobian of the infected subsystem—composed of the infected compartments of the ODE system: *I* E,
*I*
and
*L**N*
—calculated at the DFE (all eigenvalues of the Jacobian were real-valued). This shows that the DFE is unstable when
*i**R*
0> 1.
*R*
0by calculating the PRCC with respect to equation (3.6)—we base our calculation of PRCC on methods used in prior studies [60]. We find that parameters related to an interaction with the environmental reservoir (the population of needles) such as
*α*and
*β*, the couplings between hosts and needles, are at least as central to HCV dynamics as parameters traditionally associated with an epidemic, such as
*π*, the birthrate of susceptibles,
*S**μ*, the combined death and cessation rate of PWID, and
*τ*, the rate of progressing to treatment (figure 3). This fortifies the notion that W.A.I.T.-specific properties dictate the spread of HCV, providing opportunities to explore more precise targeting by public health interventions.

### 3.5 HCV W.A.I.T. model and simulated interventions: needle exchange programmes

Having demonstrated the relevance of injection drug equipment in terms of how it influences the basic reproductive number, we can consider the utility of the model with respect to other properties, including how it offers insight into potential interventions.
figure 4
*b*, we demonstrate how changing
*k*
and
*u**k*
modifies the value of
*i**R*
0. Notice that
*R*
0is reduced by increasing
*k*
across fixed values of
*i**k*, and the opposite effect—increasing
*u**R*
0—is observed when increasing
*k*
along fixed values of
*u**k*. That is, removing infected needles at an increased rate may decrease infection risk in a population of PWID, while removing uninfected needles can increase the risk. One can also see that increasing
*i**k*
and
*u**k*
simultaneously, along the dashed line—where
*i**k*
=
*u**k*
—will increase
*i**R*
0. This suggests that if a distinction between infected and uninfected needles cannot be established (as is often the case) then discarding needles indiscriminately can potentially exacerbate the spread of the infection.
*k*:=
*k*
=
*u**k*, the expression for
*i**R*
0is proportional to
We highlight this to show the explicit dependence on *k* in the *R*0 expression. Notice that this factor is monotonically increasing in *k*, indicating that no matter the values of other parameters in the model, as long as they are all positive, *R*0 will necessarily *increase* with *k*. Notice also that when = 0, the *k* dependence cancels out entirely. This indicates that when = 0, meaning that there is no flow of infected needles back to the uninfected compartment, then *R*0 is not modified by the discard rate of needles. We point the reader to the electronic supplementary material, appendix, for a more thorough discussion of this point.
figure 5). A high value would indicate a scenario where needles move quickly from an infected state to an uninfected state. This would apply to settings where viral decay on a needle is high, or when infected needles are directly exchanged for uninfected ones (as in certain needle exchange programmes). The model is run with all uninfected populations initialized at their DFE values (*S*= 170 000 and
*N*
= 220 000), and we initialize
*u**I*
=
*E**N*
= 1, and
*u**I*
= 0. In the high scenario, we observe generally slower dynamics and higher overall susceptible population sizes, along with lower infected populations (on long time scales).
*L*## 4 Discussion
While diseases transmitted through injection drug use have been the object of prior modelling efforts, none have specifically investigated how injection equipment plays a role in the dynamics of HCV. Prior models of injection equipment have focused on HIV [24,25], and/or been so complicated that their structure is not easily translated to any other settings [23]. In this study, we model HCV as an indirectly transmitted infection, where the injection equipment is modelled as the environmental reservoir, just as a water source might be modelled in a waterborne infection [8,19]. We label our approach as the W.A.I.T. model, one that incorporates features of other approaches to studying environmentally transmitted pathogens [6,11], but grounding them in a flexible model that can be neatly applied to HCV. Our approach offers several specific insights. For example, we demonstrate that the composite *R*0 that defines the entire dynamical system is the geometric mean of *R*0 values used to describe each of two sub-components: disease flow through the hosts and flow through the injection equipment (equation (3.7)). This observation offers a practical suggestion for studying diseases like HCV: epidemiologists and modellers must understand, through empirical studies, properties of all major actors in the system (hosts and environmental injection drug equipment in the case of HCV).
The mathematical model of HCV presented in this paper (described as a W.A.I.T. model; see §§[2](#s2) and [3](#s3)) also offers nuanced findings about the dynamics of disease. Firstly, our model highlights the differing roles of uninfected and infected injection on disease dynamics. Specifically, the model speaks to the potential utility of harm reduction policies: indiscriminately removing injection equipment from a system—without an overall shift in needle populations from infected to uninfected—might increase the rate of infection. In order to attenuate an epidemic, intervention strategies should focus on steering the population of needles towards being more uninfected. Therefore, ideal intervention efforts should aim to decrease sharing events on an infected needle. This helps to explain why programmes like safe injection might be effective [61]: they do not change the number of infected needles in the system directly, but can alter the sharing rate, and consequently, the probability of sharing an infected needle.
Finally, understanding the dynamical properties of disease transmitted through injection drug use is now especially relevant as a result of the modern opioid epidemic. This epidemic is typified by recreational use of prescription and illicit opioids, with injection drug use being a major route through which drugs are consumed [42]. The relevance of viral diseases among opioid users gained national attention during a 2015 outbreak of HIV in rural Indiana that was driven by an injected opioid called oxymorphone [62,63]. This outbreak raised alarms in the public health community, and officials are increasingly aware of the potential for future outbreaks. However, it was not until relatively recently that the role of the opioid crisis in HCV transmission has been examined [64,65]. We propose, in closing, that modelling approaches (in general, and not relegated to the methods proposed in this study) are crucial for understanding, attenuating or preventing explosive outbreaks of HCV in an age when a new opioid epidemic has emerged.

## Figures

- Figure
- Figure
- Figure
- Figure
- Figure

## References (65 total, showing 65)

- Dick EC, Jennings LC, Mink KA, Wartgow CD, Inborn SL. Aerosol transmission of rhinovirus colds. J. Infect. Dis.. 1987
- Abad FX, Pinto RM, Bosch A. Survival of enteric viruses on environmental fomites. Appl. Environ. Microbiol.. 1994
- Codeço CT. Endemic and epidemic dynamics of cholera: the role of the aquatic reservoir. BMC Infect. Dis.. 2001
- Boone SA, Gerba CP. Significance of fomites in the spread of respiratory and enteric viral disease. Appl. Environ. Microbiol.. 2007
- Weber TP, Stilianakis NI. Inactivation of influenza a viruses in the environment and modes of transmission: a critical review. J. Infect.. 2008
- Li S, Eisenberg JNS, Spicknall IH, Koopman JS. Dynamics and control of infections transmitted from person to person through the environment. Am. J. Epidemiol.. 2009
- Tellier R. Aerosol transmission of influenza a virus: a review of new studies. J. R. Soc. Interface. 2009
- Tien JH, Earn DJD. Multiple transmission pathways and disease dynamics in a waterborne pathogen model. Bull. Math. Biol.. 2010
- Bani-Yaghoub M, Gautam R, Shuai Z, Van Den Driessche P, Ivanek R. Reproduction numbers for infections with free-living pathogens growing in the environment. J. Biol. Dyn.. 2012
- Zhao J, Eisenberg JE, Spicknall IH, Li S, Koopman JS. Model analysis of fomite mediated influenza transmission. PLoS ONE. 2012
- Breban R. Role of environmental persistence in pathogen transmission: a mathematical modeling approach. J. Math. Biol.. 2013
- Cortez MH, Weitz JS. Distinguishing between indirect and direct modes of transmission using epidemiological time series. Am. Nat.. 2013
- Van Doremalen N, Bushmaker T, Munster VJ. Stability of Middle East respiratory syndrome coronavirus (MERS-COV) under different environmental conditions. Eurosurveillance. 2013
- Li M, Ma J, van den Driessche P. Model for disease dynamics of a waterborne pathogen on a random network. J. Math. Biol.. 2015
- Caraco T, Cizauskas CA, Wang N. Environmentally transmitted parasites: host-jumping in a heterogeneous environment. J. Theor. Biol.. 2016
- Brouwer AF, Eisenberg MC, Remais JV, Collender PA, Meza R, Eisenberg JNS. Modeling biphasic environmental decay of pathogens and implications for risk analysis. Environ. Sci. Technol.. 2017
- Brouwer AF, Weir MH, Eisenberg MC, Meza R, Eisenberg JNS. Dose-response relationships for environmentally mediated infectious disease transmission models. PLoS Comput. Biol.. 2017
- Webster JP, Borlase A, Rudge JW. Who acquires infection from whom and how? Disentangling multi-host and multi-mode transmission dynamics in the ‘elimination’ era. Phil. Trans. R. Soc. B. 2017
- Walther BA, Ewald PW. Pathogen survival in the external environment and the evolution of virulence. Biol. Rev.. 2004
- Kaplan EH. Modeling HIV infectivity: must sex acts be counted?. J. Acquir. Immune Defic. Syndr.. 1990
- Phillips AN. Reduction of concentration during acute infection: independence from a specific immune response. Science. 1996
- Kaplan EH. Needles that kill: modeling human immunodeficiency virus transmission via shared drug injection equipment in shooting galleries. Rev. Infect. Dis.. 1989
- Homer JB, St.-Clair CL. A model of HIV transmission through needle sharing. Interfaces. 1991
- Kaplan EH, Heimer R. A model-based estimate of HIV infectivity via needle sharing. J. Acquir. Immune Defic. Syndr.. 1992
- Kaplan EH, O’Keefe E. Let the needles do the talking! Evaluating the New Haven needle exchange. Interfaces. 1993
- Vickerman P, Martin N, Turner K, Hickman M. Can needle and syringe programmes and opiate substitution therapy achieve substantial reductions in hepatitis C virus prevalence? model projections for different epidemic settings. Addiction. 2012
- Martin NK. Hepatitis C virus treatment for prevention among people who inject drugs: modeling treatment scale-up in the age of direct-acting antivirals. Hepatology. 2013
- Fraser H. Model projections on the impact of HCV treatment in the prevention of HCV transmission among people who inject drugs in Europe. J. Hepatol.. 2018
- Rolls DA, Daraganova G, Sacks-Davis R, Hellard M, Jenkinson R, McBryde E. Modelling hepatitis C transmission over a social network of injecting drug users. J. Theor. Biol.. 2012
- Pitcher AB, Borquez A, Skaathun B, Martin NK. Mathematical modeling of hepatitis C virus (HCV) prevention among people who inject drugs: a review of the literature and insights for elimination strategies. J. Theor. Biol
- Cousien A, Tran VC, Deuffic-Burban S, Jauffret-Roustide M, Dhersin JS, Yazdanpanah Y. Dynamic modelling of hepatitis C virus transmission among people who inject drugs: a methodological review. J. Viral Hepat.. 2015
- Esposito N, Rossi C. A nested-epidemic model for the spread of hepatitis C among injecting drug users. Math. Biosci.. 2004
- Corson S, Greenhalgh D, Hutchinson SJ. A time since onset of injection model for hepatitis C spread amongst injecting drug users. J. Math. Biol.. 2013
- Corson S, Greenhalgh D, Hutchinson S. Mathematically modelling the spread of hepatitis C in injecting drug users. Math. Med. Biol.. 2012
- Echevarria D, Gutfraind A, Boodram B, Major M, Del Valle S, Cotler SJ. Mathematical modeling of hepatitis C prevalence reduction with antiviral treatment scale-up in persons who inject drugs in metropolitan Chicago. PLoS ONE. 2015
- Massad E, Coutinho FA, Yang HM, De Carvalho HB, Mesquita F, Burattini MN. The basic reproduction ratio of among intravenous drug users. Math. Biosci.. 1994
- Mandal S, Sarkar RR, Sinha S. Mathematical models of malaria—a review. Malar. J.. 2011
- Almagro-Moreno S, Taylor RK. Cholera: environmental reservoirs and impact on disease transmission. Microbiol. Spectr.. 2013
- National Research Council. 1995
- Van Den Berg C, Smit C, Van Brussel G, Coutinho R, Prins M. Full participation in harm reduction programmes is associated with decreased risk for human immunodeficiency virus and hepatitis C virus: evidence from the Amsterdam cohort studies among drug users. Addiction. 2007
- Lankenau SE, Teti M, Silva K, Bloom JJ, Harocopos A, Treese M. Initiation into prescription opioid misuse amongst young injection drug users. Int. J. Drug Policy. 2012
- Marshall BDL, Krieger MS, Yedinak JL, Ogera P, Banerjee P, Alexander-Scott NE. Epidemiology of fentanyl-involved drug overdose deaths: a geospatial retrospective study in Rhode Island, USA. Int. J. Drug Policy. 2017
- Jones JH. 2007
- Diekmann O, Heesterbeek JAP, Roberts MG. The construction of next-generation matrices for compartmental epidemic models. J. R. Soc. Interface. 2010
- Des Jarlais DC. Declining seroprevalence in a very large epidemic: injecting drug users in New York City, 1991 to 1996. Am. J. Public Health. 1998
- Terrault NA. Sexual transmission of hepatitis C virus among monogamous heterosexual couples: the HCV partners study. Hepatology. 2013
- Canadian Paediatric Society. Needle stick injuries in the community. Paediatr. Child Health. 2008
- Paintsil E, He H, Peters C, Lindenbach BD, Heimer R. Survival of hepatitis C virus in syringes: implication for transmission among injection drug users. J. Infect. Dis.. 2010
- Martin NK, Pitcher AB, Vickerman P, Vassall A, Hickman M. Optimal control of hepatitis C antiviral treatment programme delivery for prevention amongst a population of injecting drug users. PLoS ONE. 2011
- Micallef JM, Kaldor JM, Dore GJ. Spontaneous viral clearance following acute hepatitis C infection: a systematic review of longitudinal studies. J. Viral Hepat.. 2006
- Short LJ, Bell DM. Risk of occupational infection with blood borne pathogens in operating and delivery room settings. Am. J. Infect. Control. 1993
- Centers for Disease Control and Prevention (CDC). Recommendations for follow-up of health-care workers after occupational exposure to hepatitis C virus. MMWR Morb. Mortal Wkly. Rep.. 1997
- Hickman M, Hope V, Brady T, Madden P, Jones S, Honor S. Hepatitis C virus (HCV) prevalence, and injecting risk behaviour in multiple sites in England in 2004. J. Viral Hepat.. 2007
- Poynard T, Bedossa P, Opolon P. Natural history of liver fibrosis progression in patients with chronic hepatitis C. Lancet. 1997
- Khan A, Sial S, Imran M. Transmission dynamics of hepatitis C with control strategies. J. Comput. Med.. 2014
- Grebely J, Conway B, Raffa J, Lai C, Krajden M, Tyndall M. Uptake of hepatitis C virus (HCV) treatment among injection drug users (IDUS) in Vancouver, Canada. J. Hepatol.. 2006
- Seal KH, Kral A, Lorvick J, Gee L, Tsui J, Edlin B. Among injection drug users, interest is high, but access low to HCV antiviral therapy. J. Gen. Intern. Med.. 2005
- Gold K. Analysis: the impact of needle, syringe, and lancet disposal on the community. J. Diabetes Sci. Technol.. 2011
- Heller DI, Paone D, Siegler A, Karpati A. The syringe gap: an assessment of sterile syringe need and acquisition among syringe exchange program participants in New York City. Harm Reduct. J.. 2009
- Blower SM, Dowlatabadi H. Sensitivity and uncertainty analysis of complex models of disease transmission: an model, as an example. Int. Stat. Rev.. 1994
- Rhodes T, Kimber J, Small W, Fitzgerald J, Kerr T, Hickman M. Public injecting and the need for ‘safer environment interventions’ in the reduction of drug-related harm. Addiction. 2006
- Conrad C. Community outbreak of HIV infection linked to injection drug use of oxymorphone—Indiana, 2015. MMWR Morb. Mortal. Wkly. Rep.. 2015
- Peters PJ. infection linked to injection use of oxymorphone in Indiana, 2014–2015. N. Engl. J. Med.. 2016
- Zibbell JE. Increases in hepatitis C virus infection related to injection drug use among persons aged ≤30 years—Kentucky, Tennessee, Virginia, and West Virginia, 2006–2012. MMWR Morb. Mortal. Wkly. Rep.. 2015
- Powell D, Alpert A, Pacula RL. A transitioning epidemic: how the opioid crisis is driving the rise in hepatitis C. Health Aff.. 2019
