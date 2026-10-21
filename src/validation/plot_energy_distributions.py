"""Save three matplotlib figures for finite building estimates only."""

import math
from pathlib import Path

import matplotlib

matplotlib.use('Agg')  # Save figures without a desktop display.
import matplotlib.pyplot as plt

if __package__:
    from .validate_energy_outputs import RATED, ANNUAL, load_energy_outputs, numeric_values, validate_structure
else:
    from validate_energy_outputs import RATED, ANNUAL, load_energy_outputs, numeric_values, validate_structure

OUTPUT_DIR = Path(__file__).resolve().parents[2] / 'outputs/validation'


def histogram(values, label: str, title: str, path: Path) -> None:
    """Use log-spaced bins only for positive data spanning at least two decades."""
    values = numeric_values(values)
    fig, ax = plt.subplots(figsize=(8, 5))
    use_log = len(values) > 0 and values.min() > 0 and values.max() / values.min() >= 100
    bins = 30
    if use_log:
        # Multiple orders of magnitude compress most sites into the first linear
        # bin. Log-spaced bins preserve detail; zero values force a linear plot.
        low, high = math.log10(values.min()), math.log10(values.max())
        bins = [10 ** (low + (high - low) * index / 30) for index in range(31)]
        bins[0], bins[-1] = values.min(), values.max()
        ax.set_xscale('log')
    ax.hist(values, bins=bins)
    ax.set_xlabel(label + (' (log scale)' if use_log else ''))
    ax.set_ylabel('Number of building sites')
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    df = validate_structure(load_energy_outputs())
    buildings = df.loc[df.site_type.eq('building') & df.energy_estimate_status.eq('estimated_building')]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    histogram(buildings[RATED], 'Estimated rated IT power (MW)',
              'Building rated IT power — scenario estimates', OUTPUT_DIR / 'rated_it_power_distribution.png')
    histogram(buildings[ANNUAL], 'Estimated annual facility energy (MWh/year)',
              'Building annual facility energy — scenario estimates', OUTPUT_DIR / 'annual_energy_distribution.png')
    points = buildings[['square_feet', RATED]].dropna()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(points.square_feet, points[RATED])
    log_axes = False
    if not points.empty and (points > 0).all().all():
        # Matching log axes expose a wide area range. Under uniform assumptions
        # the straight line is imposed by the model, not independent validation.
        if (points.max() / points.min()).min() >= 100:
            ax.set_xscale('log')
            ax.set_yscale('log')
            log_axes = True
    suffix = ' (log scale)' if log_axes else ''
    ax.set_xlabel('IM3 building footprint (ft²)' + suffix)
    ax.set_ylabel('Estimated rated IT power (MW)' + suffix)
    ax.set_title('Building footprint vs. rated IT power — scenario estimates')
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / 'footprint_vs_power.png', dpi=150)
    plt.close(fig)
    print(f'Saved three figures to {OUTPUT_DIR}')


if __name__ == '__main__':
    main()
