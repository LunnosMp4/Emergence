![Demo](resources/demo.gif)

# Emergence

Emergence is a solo zero-player ecosystem sandbox: you press run, then observe a prey/predator world evolve from simple rules.

## Main Concept

- Prey agents search for food, avoid danger, and evolve over generations.
- Predator agents hunt prey, manage energy, and reproduce more slowly.
- Communication happens through pheromone fields (danger, relay, distress, kill-site, mate).
- Reproduction is partner-based (seek mate -> contact -> mating duration -> cooldown).
- Adaptive balancing helps the simulation avoid easy collapse.

## Main Rules

1. Food spawns over time up to a max limit.
2. Every movement costs energy; speed/size traits change the cost.
3. Prey prioritize survival: threat detection and pheromone danger can override other goals.
4. Both species need enough energy and valid mate conditions to reproduce.
5. Mating is not instant: agents must touch and stay coupled for a required duration.
6. Reproduction has cooldowns and energy costs, so growth is naturally limited.
7. Predator population is capped by MAX_CARNIVORES.
8. When predator cap is reached, predators do not enter seek-mate mode.
9. Pheromone signals decay over time and are species-filtered where needed.
10. An agent dies when its energy reaches zero.

## Run

```bash
pip install -r requirements.txt
python main.py
```

Optional control: press `V` in the simulation to toggle pheromone debug rendering.