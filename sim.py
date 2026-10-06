import numpy as np
from scipy import special
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

surface_tension = 0.0728 # N/m
density = 1000 # kg/m^3
gravity = 9.81 # m/s^2
radius = 0.003 # m

FPS = 3000
SIM_HEIGHT = 0.03
VIEW_HEIGHT = 0.03
RESOLUTION = 600
DAMPING = 5e-6
JET_VELOCITY = 0.4
AMPLITUDE = 0.6

def freq(k, radius):
    """Calculate the angular frequency for a given wavenumber."""
    alpha = k * radius
    value = (surface_tension / density / radius**3) *\
            (special.i1(alpha) / special.i0(alpha)) *\
            alpha * (alpha ** 2 - 1)

    return np.where(value > 0, np.emath.sqrt(value), -np.emath.sqrt(value))

y = np.arange(0, SIM_HEIGHT, SIM_HEIGHT / RESOLUTION)
k = np.fft.rfftfreq(RESOLUTION, SIM_HEIGHT / RESOLUTION) * 2 * np.pi
clip_pos = int((VIEW_HEIGHT / SIM_HEIGHT) * RESOLUTION)
clipped_y = y[:clip_pos]

def update(frame):
    t = frame / FPS
    omega = freq(k, radius)
    omega -= JET_VELOCITY * k
    damping = DAMPING * k ** 2
    comp_damping = -damping - 1j * omega
    ab = 1 / comp_damping

    spectrum = ab * np.exp(t * comp_damping) - ab
    spectrum[0] = 0
    #spectrum[omega < 0] = 0
    wave = np.fft.irfft(spectrum).real * AMPLITUDE
    wave = wave[:clip_pos]

    ax.clear()
    ax.set_xlim(-5 * radius, 5 * radius)
    ax.plot(-wave - radius, clipped_y, c="tab:blue")
    ax.plot(wave + radius, clipped_y, c="tab:blue")

fig, ax = plt.subplots()
ani = FuncAnimation(fig, update, interval=1000 / 30)

plt.show()
