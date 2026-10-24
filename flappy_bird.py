"""
Flappy Bird - Animated Edition
==============================
Upgrades over the original:
  * Flapping bird animation (3 wing frames) + tilt that follows the fall/flap speed
  * Scrolling ground (base) that moves at the same speed as the pipes
  * Parallax background: slowly scrolling scenery + drifting clouds
  * Day / night cycle (changes every 10 points) with fading stars
  * Idle bobbing bird on the welcome screen (the old screen only redrew on events)
  * Death animation + GAME OVER panel
  * Fairer rectangle collision
  * Works even if some sprites / sounds are missing (it draws its own)

Put this file NEXT TO your `gallery` folder:

    flappy_bird.py
    gallery/sprites/bird.png, background.png, pipe.png, base.png, message.png, 0-9.png
    gallery/audio/die.wav, hit.wav, point.wav, swoosh.wav, wing.wav

Optional: for a hand-drawn wing animation add these three sprites
    gallery/sprites/bird_up.png   gallery/sprites/bird_mid.png   gallery/sprites/bird_down.png
Without them, frames are made automatically from bird.png.
"""
import math
import os
import random
import sys

import pygame
from pygame.locals import *

# ----------------------------------------------------------------- settings
FPS = 32
SCREENWIDTH = 289
SCREENHEIGHT = 511
GROUNDY = SCREENHEIGHT * 0.8
PIPE_SPEED = -4          # pipes and ground move at this speed
BG_SPEED = 1             # background scroll speed (slower = looks farther away)
WING_TICKS = 3           # frames per wing animation step (lower = faster flap)
NIGHT_EVERY = 10         # score interval for day <-> night switch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GAME_SPRITES = {}
GAME_SOUNDS = {}
BIRD_FRAMES = []         # wing sequence: mid, up, mid, down
SCREEN = None
FPSCLOCK = None


def asset(*parts):
    return os.path.join(BASE_DIR, 'gallery', *parts)


# ------------------------------------------------------------ asset helpers
def load_image(name, alpha=True):
    path = asset('sprites', name)
    if os.path.exists(path):
        try:
            img = pygame.image.load(path)
            return img.convert_alpha() if alpha else img.convert()
        except pygame.error:
            return None
    return None


class _Silent:
    def play(self):
        pass


def load_sound(name):
    path = asset('audio', name)
    if os.path.exists(path):
        try:
            return pygame.mixer.Sound(path)
        except pygame.error:
            pass
    return _Silent()


def render_text(text, size, color=(255, 255, 255), outline=(30, 30, 30)):
    font = pygame.font.Font(None, size)
    fill = font.render(text, True, color)
    edge = font.render(text, True, outline)
    w, h = fill.get_size()
    surf = pygame.Surface((w + 4, h + 4), SRCALPHA)
    for dx, dy in ((0, 0), (4, 0), (0, 4), (4, 4), (2, 0), (0, 2), (4, 2), (2, 4)):
        surf.blit(edge, (dx, dy))
    surf.blit(fill, (2, 2))
    return surf


# ------------------------------------------------- fallback (drawn) sprites
def make_bird(wing):
    """wing: -1 up, 0 middle, 1 down"""
    s = pygame.Surface((34, 24), SRCALPHA)
    pygame.draw.ellipse(s, (250, 200, 40), (2, 3, 28, 19))
    pygame.draw.ellipse(s, (190, 130, 20), (2, 3, 28, 19), 2)
    pygame.draw.circle(s, (255, 255, 255), (23, 9), 5)
    pygame.draw.circle(s, (0, 0, 0), (25, 9), 2)
    pygame.draw.polygon(s, (240, 100, 40), [(28, 13), (34, 15), (28, 19)])
    wy = 11 + wing * 4
    pygame.draw.ellipse(s, (255, 235, 160), (5, wy - 2, 13, 8))
    pygame.draw.ellipse(s, (190, 130, 20), (5, wy - 2, 13, 8), 1)
    return s


def make_pipe():
    w, h = 52, 320
    s = pygame.Surface((w, h), SRCALPHA)
    pygame.draw.rect(s, (115, 190, 46), (3, 24, w - 6, h - 24))
    pygame.draw.rect(s, (160, 225, 90), (7, 24, 8, h - 24))
    pygame.draw.rect(s, (80, 140, 30), (w - 12, 24, 8, h - 24))
    pygame.draw.rect(s, (60, 100, 25), (3, 24, w - 6, h - 24), 2)
    pygame.draw.rect(s, (115, 190, 46), (0, 0, w, 24))
    pygame.draw.rect(s, (160, 225, 90), (4, 3, 8, 18))
    pygame.draw.rect(s, (60, 100, 25), (0, 0, w, 24), 2)
    return s


def make_base():
    w, h = 336, 112
    s = pygame.Surface((w, h))
    s.fill((222, 216, 149))
    for x in range(-24, w + 24, 24):          # period divides width -> seamless
        pygame.draw.polygon(s, (205, 198, 130), [(x, 12), (x + 12, 12), (x + 24, h), (x + 12, h)])
    pygame.draw.rect(s, (115, 190, 46), (0, 0, w, 12))
    pygame.draw.rect(s, (160, 225, 90), (0, 0, w, 4))
    pygame.draw.line(s, (80, 130, 30), (0, 12), (w, 12), 2)
    return s


def make_background():
    s = pygame.Surface((SCREENWIDTH, SCREENHEIGHT))
    for y in range(SCREENHEIGHT):
        t = y / SCREENHEIGHT
        c = (int(70 + 110 * t), int(170 + 55 * t), int(235 + 15 * t))
        pygame.draw.line(s, c, (0, y), (SCREENWIDTH, y))
    layers = [((130, 205, 180), 50, 30, 1, 0.5), ((90, 175, 130), 30, 4, 2, 2.0)]
    for color, amp, off, k, phase in layers:
        for x in range(SCREENWIDTH):
            y = GROUNDY - off - amp * (0.5 + 0.5 * math.sin(2 * math.pi * k * x / SCREENWIDTH + phase))
            pygame.draw.line(s, color, (x, int(y)), (x, int(GROUNDY)))
    return s


def make_cloud(w):
    h = int(w * 0.5)
    s = pygame.Surface((w, h), SRCALPHA)
    for cx, cy, r in ((0.25, 0.65, 0.25), (0.45, 0.45, 0.32), (0.68, 0.6, 0.27), (0.85, 0.7, 0.18)):
        pygame.draw.circle(s, (255, 255, 255, 215), (int(w * cx), int(h * cy)), int(w * r * 0.6))
    pygame.draw.rect(s, (255, 255, 255, 215), (int(w * 0.15), int(h * 0.65), int(w * 0.7), int(h * 0.3)))
    return s


# ------------------------------------------------------------ load assets
def make_bird_frames(img):
    """Build wing frames from one bird.png by squash & stretch."""
    w, h = img.get_size()
    up = pygame.transform.smoothscale(img, (max(1, int(w * 0.92)), max(1, int(h * 1.14))))
    down = pygame.transform.smoothscale(img, (max(1, int(w * 1.07)), max(1, int(h * 0.86))))
    return [img, up, img, down]


def load_assets():
    GAME_SPRITES['numbers'] = tuple(
        load_image('%d.png' % i) or render_text(str(i), 56) for i in range(10))
    GAME_SPRITES['message'] = load_image('message.png') or _make_message()
    GAME_SPRITES['base'] = load_image('base.png') or make_base()

    pipe = load_image('pipe.png') or make_pipe()
    GAME_SPRITES['pipe'] = (pygame.transform.rotate(pipe, 180), pipe)

    bg = load_image('background.png', alpha=False) or make_background()
    GAME_SPRITES['background'] = pygame.transform.scale(bg, (SCREENWIDTH, SCREENHEIGHT))

    up, mid, down = load_image('bird_up.png'), load_image('bird_mid.png'), load_image('bird_down.png')
    single = load_image('bird.png')
    if up and mid and down:
        frames = [mid, up, mid, down]
        GAME_SPRITES['player'] = mid
    elif single:
        frames = make_bird_frames(single)
        GAME_SPRITES['player'] = single
    else:
        frames = [make_bird(0), make_bird(-1), make_bird(0), make_bird(1)]
        GAME_SPRITES['player'] = frames[0]
    BIRD_FRAMES[:] = frames

    for name in ('die', 'hit', 'point', 'swoosh', 'wing'):
        GAME_SOUNDS[name] = load_sound(name + '.wav')


def _make_message():
    s = pygame.Surface((184, 140), SRCALPHA)
    t1 = render_text('FLAPPY BIRD', 44, (255, 220, 60))
    t2 = render_text('Press SPACE / UP', 26)
    s.blit(t1, ((184 - t1.get_width()) // 2, 20))
    s.blit(t2, ((184 - t2.get_width()) // 2, 90))
    return s


# --------------------------------------------------------------- scenery
class Scenery:
    """Scrolling background, clouds, stars, ground and the day/night tint."""

    def __init__(self):
        bg = GAME_SPRITES['background']
        # mirror-tiled strip => endless scroll with no visible seam
        self.strip = pygame.Surface((SCREENWIDTH * 2, SCREENHEIGHT))
        self.strip.blit(bg, (0, 0))
        self.strip.blit(pygame.transform.flip(bg, True, False), (SCREENWIDTH, 0))
        self.bgx = 0.0

        self.cloud_imgs = [make_cloud(w) for w in (50, 70, 95)]
        self.clouds = [{
            'img': random.choice(self.cloud_imgs),
            'x': random.uniform(0, SCREENWIDTH),
            'y': random.uniform(15, SCREENHEIGHT * 0.40),
            'v': random.uniform(0.3, 0.8),
        } for _ in range(5)]

        self.stars = pygame.Surface((SCREENWIDTH, SCREENHEIGHT), SRCALPHA)
        for _ in range(45):
            x, y = random.randrange(SCREENWIDTH), random.randrange(int(SCREENHEIGHT * 0.6))
            pygame.draw.circle(self.stars, (255, 255, 240), (x, y), random.choice((1, 1, 2)))

        self.overlay = pygame.Surface((SCREENWIDTH, SCREENHEIGHT))
        self.overlay.fill((8, 12, 48))
        self.night = 0.0
        self.basex = 0

    def update(self, score=0, moving=True):
        if not moving:
            return
        self.bgx = (self.bgx + BG_SPEED) % (SCREENWIDTH * 2)
        self.basex = (self.basex + abs(PIPE_SPEED)) % GAME_SPRITES['base'].get_width()
        for c in self.clouds:
            c['x'] -= c['v']
            if c['x'] < -c['img'].get_width():
                c['x'] = SCREENWIDTH + random.uniform(0, 60)
                c['y'] = random.uniform(15, SCREENHEIGHT * 0.40)
                c['img'] = random.choice(self.cloud_imgs)
                c['v'] = random.uniform(0.3, 0.8)
        target = 1.0 if (score // NIGHT_EVERY) % 2 == 1 else 0.0
        self.night += (target - self.night) * 0.02

    def draw_back(self):
        x = int(self.bgx)
        SCREEN.blit(self.strip, (-x, 0))
        SCREEN.blit(self.strip, (SCREENWIDTH * 2 - x, 0))
        if self.night > 0.02:
            self.stars.set_alpha(int(self.night * 255))
            SCREEN.blit(self.stars, (0, 0))
        for c in self.clouds:
            SCREEN.blit(c['img'], (int(c['x']), int(c['y'])))

    def draw_ground(self):
        base = GAME_SPRITES['base']
        bw = base.get_width()
        x = -self.basex
        while x < SCREENWIDTH:
            SCREEN.blit(base, (x, GROUNDY))
            x += bw
        if self.night > 0.02:                       # darken pipes + ground at night
            self.overlay.set_alpha(int(self.night * 120))
            SCREEN.blit(self.overlay, (0, 0))


# ------------------------------------------------------------- drawing utils
def draw_bird(frame, x, y, angle):
    pw, ph = GAME_SPRITES['player'].get_size()
    rot = pygame.transform.rotate(frame, angle)
    SCREEN.blit(rot, rot.get_rect(center=(x + pw / 2, y + ph / 2)))


def draw_score(score):
    digits = [int(d) for d in str(score)]
    width = sum(GAME_SPRITES['numbers'][d].get_width() for d in digits)
    xoff = (SCREENWIDTH - width) / 2
    for d in digits:
        SCREEN.blit(GAME_SPRITES['numbers'][d], (xoff, SCREENHEIGHT * 0.12))
        xoff += GAME_SPRITES['numbers'][d].get_width()


def poll_events():
    """Handle quit keys and return the remaining events."""
    events = pygame.event.get()
    for e in events:
        if e.type == QUIT or (e.type == KEYDOWN and e.key == K_ESCAPE):
            pygame.quit()
            sys.exit()
    return events


def is_flap(e):
    return (e.type == KEYDOWN and e.key in (K_SPACE, K_UP)) or e.type == MOUSEBUTTONDOWN


# ------------------------------------------------------------------ screens
def welcomeScreen(scenery):
    pw, ph = GAME_SPRITES['player'].get_size()
    playerx = int(SCREENWIDTH / 5)
    base_y = int((SCREENHEIGHT - ph) / 2)
    msg = GAME_SPRITES['message']
    msgx = int((SCREENWIDTH - msg.get_width()) / 2)
    msgy = int(SCREENHEIGHT * 0.13)
    t = 0
    while True:
        for e in poll_events():
            if is_flap(e):
                GAME_SOUNDS['swoosh'].play()
                return
        scenery.update(0, True)
        scenery.draw_back()
        scenery.draw_ground()
        bob = math.sin(t * 0.15) * 6
        draw_bird(BIRD_FRAMES[(t // WING_TICKS) % 4], playerx, base_y + bob, bob * 1.5)
        SCREEN.blit(msg, (msgx, msgy))
        pygame.display.update()
        FPSCLOCK.tick(FPS)
        t += 1


def getRandomPipe():
    pipeHeight = GAME_SPRITES['pipe'][0].get_height()
    offset = SCREENHEIGHT / 3
    y2 = offset + random.randrange(0, int(SCREENHEIGHT - GAME_SPRITES['base'].get_height() - 1.2 * offset))
    pipeX = SCREENWIDTH + 10
    y1 = pipeHeight - y2 + offset
    return [
        {'x': pipeX, 'y': -y1},   # upper pipe
        {'x': pipeX, 'y': y2},    # lower pipe
    ]


def isCollide(playerx, playery, upperPipes, lowerPipes):
    bw, bh = GAME_SPRITES['player'].get_size()
    if playery + bh >= GROUNDY - 1 or playery < 0:
        return True
    bird = pygame.Rect(int(playerx) + 4, int(playery) + 4, bw - 8, bh - 8)   # slightly forgiving
    pw, ph = GAME_SPRITES['pipe'][0].get_size()
    for up, low in zip(upperPipes, lowerPipes):
        if bird.colliderect(pygame.Rect(int(up['x']), int(up['y']), pw, ph)):
            return True
        if bird.colliderect(pygame.Rect(int(low['x']), int(low['y']), pw, ph)):
            return True
    return False


def mainGame(scenery):
    score = 0
    bw, bh = GAME_SPRITES['player'].get_size()
    playerx = int(SCREENWIDTH / 5)
    playery = int((SCREENHEIGHT - bh) / 2)

    newPipe1, newPipe2 = getRandomPipe(), getRandomPipe()
    upperPipes = [
        {'x': SCREENWIDTH + 200, 'y': newPipe1[0]['y']},
        {'x': SCREENWIDTH + 200 + (SCREENWIDTH / 2), 'y': newPipe2[0]['y']},
    ]
    lowerPipes = [
        {'x': SCREENWIDTH + 200, 'y': newPipe1[1]['y']},
        {'x': SCREENWIDTH + 200 + (SCREENWIDTH / 2), 'y': newPipe2[1]['y']},
    ]

    playerVelY = -9
    playerMaxVelY = 10
    playerAccY = 1
    playerFlapAccv = -8
    playerFlapped = False
    tick = 0
    pipe_w = GAME_SPRITES['pipe'][0].get_width()

    def render(by, angle, widx):
        scenery.draw_back()
        for u, l in zip(upperPipes, lowerPipes):
            SCREEN.blit(GAME_SPRITES['pipe'][0], (int(u['x']), int(u['y'])))
            SCREEN.blit(GAME_SPRITES['pipe'][1], (int(l['x']), int(l['y'])))
        scenery.draw_ground()
        draw_bird(BIRD_FRAMES[widx], playerx, by, angle)
        draw_score(score)

    while True:
        for e in poll_events():
            if is_flap(e) and playery > 0:
                playerVelY = playerFlapAccv
                playerFlapped = True
                GAME_SOUNDS['wing'].play()

        if isCollide(playerx, playery, upperPipes, lowerPipes):
            break

        # score
        playerMidPos = playerx + bw / 2
        for pipe in upperPipes:
            pipeMidPos = pipe['x'] + pipe_w / 2
            if pipeMidPos <= playerMidPos < pipeMidPos + 4:
                score += 1
                print(f"Your score is {score}")
                GAME_SOUNDS['point'].play()

        # bird physics
        if playerVelY < playerMaxVelY and not playerFlapped:
            playerVelY += playerAccY
        if playerFlapped:
            playerFlapped = False
        playery = playery + min(playerVelY, GROUNDY - playery - bh)

        # pipes
        for u, l in zip(upperPipes, lowerPipes):
            u['x'] += PIPE_SPEED
            l['x'] += PIPE_SPEED
        if 0 < upperPipes[0]['x'] < 5:
            newpipe = getRandomPipe()
            upperPipes.append(newpipe[0])
            lowerPipes.append(newpipe[1])
        if upperPipes[0]['x'] < -pipe_w:
            upperPipes.pop(0)
            lowerPipes.pop(0)

        scenery.update(score, True)

        angle = max(-70, min(25, -playerVelY * 6))      # nose up when flapping, down when falling
        render(playery, angle, (tick // WING_TICKS) % 4)
        pygame.display.update()
        FPSCLOCK.tick(FPS)
        tick += 1

    # ---- crash: hit sound, small bounce, fall to the ground, GAME OVER
    GAME_SOUNDS['hit'].play()
    GAME_SOUNDS['die'].play()
    vel, angle = -5, 20
    while playery + bh < GROUNDY - 1:
        poll_events()
        vel = min(vel + 2, 14)
        playery = min(playery + vel, GROUNDY - bh)
        angle = max(angle - 9, -90)
        scenery.update(score, False)
        render(playery, angle, 0)
        pygame.display.update()
        FPSCLOCK.tick(FPS)

    title = render_text('GAME OVER', 52, (255, 90, 60))
    info = render_text('Score: %d' % score, 36)
    for _ in range(int(FPS * 1.4)):
        poll_events()
        render(playery, -90, 0)
        SCREEN.blit(title, ((SCREENWIDTH - title.get_width()) // 2, int(SCREENHEIGHT * 0.30)))
        SCREEN.blit(info, ((SCREENWIDTH - info.get_width()) // 2, int(SCREENHEIGHT * 0.30) + 55))
        pygame.display.update()
        FPSCLOCK.tick(FPS)


# --------------------------------------------------------------------- main
if __name__ == "__main__":
    pygame.init()
    FPSCLOCK = pygame.time.Clock()
    SCREEN = pygame.display.set_mode((SCREENWIDTH, SCREENHEIGHT))
    pygame.display.set_caption('Flappy Bird - Animated')
    load_assets()
    scenery = Scenery()
    while True:
        welcomeScreen(scenery)
        mainGame(scenery)
