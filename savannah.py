#!/usr/bin/python3
# Requires mesa: sudo python3 m pip install mesa
# Requires tkinter: sudo apt install python3-tk

import re
import math
import time
import datetime
import random
import itertools
import mesa.time
import tkinter as tk
from tkinter import ttk
from mesa import Agent, Model
from mesa.space import ContinuousSpace


# User configurable variables (via sliders)
ROCKY_AREAS = 0.02  		# Percent of grass that is rocky.
AGE_T = 0.005  				# How much to advance age each tick
GRASS_REGROW = 2  			# Regrow grass every 2 years
BABIES_PER_TIGER_PREGS = 2
BABIES_PER_PREY_PREGS = 3.5
FOOD_PER_TICK = .3
LIFESPAN_TIGER = 17
LIFESPAN_PREY = 9
RADIUS_PREY = 2
RADIUS_TIGER = 9
TICK_DELAY = 10
NUM_TICKS = 100
START_TIME = None
MAX_TICKS = NUM_TICKS


def get_speed(cur_age, max_age, max_speed):
    '''Given the age and max speed, computer current speed'''
    x = cur_age / max_age
    if x > 1:
        x = 1
    if x < 0.5:
        y = (-(2 * x - 1)**4 + 1)
    else:
        x -= 0.5
        y = 5.1*x**3-6.4*x**2+0.6*x+1

    if y <= 0.1:
        y = 0.1
    return y * max_speed


def norm_distro(center):
    '''Return a normal distribution around center'''
    return (random.normalvariate(0, 0.2)+1) * center


def pos_box(pos, size=8):
    '''Get the CANVAS coords to draw a box on the grid'''
    x_1, y_1 = pos
    x_1 = x_1*10 + CANVAS_MARGIN - 5
    y_1 = y_1*10 + CANVAS_MARGIN - 5
    x_2 = x_1 + size
    y_2 = y_1 + size
    return (x_1, y_1, x_2, y_2)


def get_distance(pos1, pos2):
    '''Distance between two points'''
    x_1, y_1 = pos1
    x_2, y_2 = pos2
    return math.sqrt((y_2-y_1)**2+(x_2-x_1)**2)


class Patch(Agent):
    '''The physical content of a given cell'''

    def __init__(self, uid, model):
        super().__init__(uid, model)
        self.uid = uid
        if random.random() < ROCKY_AREAS:
            self.type = 'Rock'
        else:
            self.type = 'Grass'

        if self.type == 'Grass':
            self.grass = 1.0
        else:
            self.grass = 0

    def regrow(self):
        self.grass = 1
        self.update()

    def get_color(self):
        if self.grass >= 1:
            return "#00FF00"
        elif self.type == 'Rock':
            return "#908F8A"
        else:
            return "#CAA800"

    def update(self):
        self.canvas.itemconfig(self.icon, fill=self.get_color())

    def munch(self):
        self.grass = 0
        self.update()
        step = int(self.model.step_num + GRASS_REGROW // AGE_T)
        g = self.model.grass_ticks.get(step, [])
        g.append(self)
        self.model.grass_ticks[step] = g

    def draw(self):
        self.icon = self.canvas.create_rectangle(*pos_box(self.pos), tags="patch", fill=self.get_color())


class Animal(Agent):
    '''Base Class for Predators and Prey'''

    def __init__(self, uid, model, age):
        super().__init__(uid, model)
        self.gender = random.randint(0, 1)  # 0 = Female 1=Male
        self.pregs = 0
        self.uid = uid
        self.target = None  	# Target patch to go towards
        self.age = age
        self.pos = (0, 0)
        self.alive = True
        self.colors = ("#000000", "#000000", "#000000")
        self.canvas = None		# Canvas to draw animal on.
        self.food = 0			# Current stomach contents
        self.type = ''			# The type of animal
        self.max_age = 9
        self.max_speed = 1

    def can_mate(self):
        '''Is this Animal ready to make babies?'''
        if self.gender == 0 and self.pregs == 0 and 8 > self.age > 1 and self.food > 50:
            return True
        else:
            return False

    def set_speed(self):
        '''Change Animal Speed'''
        self.speed = get_speed(self.age, self.max_age, self.max_speed)
        if self.pregs:
            self.speed -= self.pregs

    def __str__(self):
        return self.type+' '+str(self.uid)

    def info(self):
        return ' '.join(map(str, (self.pos, self.food)))+':'

    def update(self):
        self.canvas.itemconfig(self.icon,
                               fill=self.colors[self.gender if not self.pregs else 2])

    def draw(self):
        fill = self.colors[self.gender]
        self.icon = self.canvas.create_oval(*pos_box(self.pos, size=12), fill=fill, tags=self.type)

    def kill(self):
        self.model.kill(self)

    def step(self):
        # print(self.type, int(self.food))
        if not self.alive:
            self.kill()
            return
        self.food -= FOOD_PER_TICK
        self.age += AGE_T
        step = self.model.step_num

        if self.food <= 0:
            print(self, 'starved to death')
            self.kill()
            return
        if self.age > self.max_age:
            print(self, 'aged out')
            self.kill()
            return

        if self.pregs:
            self.food -= FOOD_PER_TICK / 3
            self.pregs += AGE_T
            if self.pregs >= 1:
                self.pregs = 0
                self.update()
                babies = (random.normalvariate(0, 0.2)+1)
                babies *= (BABIES_PER_TIGER_PREGS
                           if self.type == 'Tiger' else BABIES_PER_PREY_PREGS)
                babies = int(round(babies, 0))
                print(self, "has given birth to", babies, 'babies')
                for x in range(babies):
                    self.model.create_baby(*self.pos, type=self.type)

        # Birthday
        if step % 10 == 0:
            self.set_speed()

        self.target = self.get_target()
        target = self.target

        if target:
            if not target.pos:
                print("Target has no position!", self, target)
                self.target = None
                return
            new_pos, delta_x, delta_y = calc_move(*self.pos, *target.pos, self.speed)
            # print("Moving:", self.pos, new_pos, delta_x, delta_y)
            x, y = new_pos
            if 0 > x > 80 or 0 > y > 80:
                # Out of bounds (rare error)
                print(vars(self), vars(target))
                print(self.pos, new_pos)
            self.model.space.move_agent(self, new_pos)
            self.canvas.coords(self.icon, *pos_box(new_pos, size=12))

    def get_target(self):
        # Look at cell neighbors and choose a target
        # self.model.space.get_neighborhood(self.pos, moore=True, include_center=True)
        # cellmates = self.model.space.get_cell_list_contents([self.pos])
        space = self.model.space
        cellmates = space.get_neighbors(self.pos, radius=3)
        random.shuffle(cellmates)

        target = self.target

        # Eat the food in current cell or look to fornicate
        if target and target.pos and get_distance(self.pos, target.pos) < .5:
            if self.type == 'Prey' and target.type == 'Grass' and self.food < 80 and target.grass >= 1:
                target.munch()
                self.food += 10
                return None

            elif self.type == 'Tiger' and target.type == 'Prey' and self.food < 80:
                print(self, 'ate', target)
                self.food += 40 + target.food / 4
                target.alive = False
                return None

            elif self.type == target.type and target.can_mate():
                print(self, 'mated with', target)
                target.pregs = 0.1
                target.update()

            else:
                target = None

        # Otherwise keep existing target
        if target:
            return target

        # If low on food find a nearby food obj
        if self.food < 80:
            if self.type == 'Prey':
                food_cells = space.get_neighbors(self.pos, radius=RADIUS_PREY)
                random.shuffle(food_cells)
                for obj in food_cells:
                    if obj.type == 'Grass':
                        if obj.grass >= 1:
                            return obj
            else:
                food_cells = space.get_neighbors(self.pos, radius=RADIUS_TIGER)
                # random.shuffle(food_cells) #unnecessary
                for obj in food_cells:
                    if obj.type == 'Prey':
                        return obj

        # Otherwise if male, try to mate:
        if self.gender == 1:
            for obj in cellmates:
                if self.type == obj.type and obj.can_mate():
                    # print(self, 'wants to mate with', obj)
                    return obj

        # Nothing else to do? Wander.
        for obj in cellmates:
            if type(obj) == Patch and obj.type == 'Grass':
                target = obj
                return obj


class Tiger(Animal):
    def __init__(self, uid, model, age=0):
        super().__init__(uid, model, age)
        self.type = 'Tiger'
        self.colors = ("#FF9933", "#FF8000", "#FFFF66")
        self.max_speed = 2
        self.max_age = norm_distro(LIFESPAN_TIGER)
        self.food = 50
        self.set_speed()


class Prey(Animal):
    '''An Animal that eats grass'''
    def __init__(self, uid, model, age=0):
        super().__init__(uid, model, age)
        self.type = 'Prey'
        self.max_speed = 1  # Maximum possible speed when at adulthood
        self.food = 10  	# 0-100
        self.max_age = norm_distro(LIFESPAN_PREY)
        self.colors = ("#F5F3EC", "#DED9C2", "#CCE5FF")  # Female, Male, Pregs colors
        self.set_speed()


def calc_move(x_1, y_1, x_2, y_2, distance):
    '''Move along a line from x_1,y_1 to x_2,y_2 at 1 unit of distance per tick'''

    delta_y = y_2 - y_1
    delta_x = x_2 - x_1
    # print("To travel:", delta_x, delta_y)
    if delta_y != 0:
        ratio = delta_x / delta_y

        delta_y = math.sqrt(distance**2 / (ratio**2 + 1)) * (-1 if delta_y < 0 else 1)
        delta_x = abs(ratio * delta_y) * (-1 if delta_x < 0 else 1)
    else:
        delta_y = 0
        delta_x = distance * (-1 if delta_x < 0 else 1)

    if abs(delta_x) > abs(x_2 - x_1) or abs(delta_y) > abs(y_2 - y_1):
        return (x_2, y_2), delta_x, delta_y
    else:
        return (x_1+delta_x, y_1+delta_y), delta_x, delta_y


class Prey_model(Model):
    def __init__(self, Prey_count, Tiger_count, width, height, CANVAS):
        self.count = 0  # Number of agents
        self.schedule = mesa.time.RandomActivation(self)
        self.space = ContinuousSpace(width+1, height+1, torus=False)
        self.step_num = 0
        self.last_uid = 0
        self.canvas = CANVAS
        self.grass_ticks = dict()
        self.Prey_count = 0
        self.Tiger_count = 0

        # Create patches
        for x, y in itertools.product(range(width), range(height)):
            a = Patch(self.new_uid(), self)
            # self.schedule.add(a)
            self.space.place_agent(a, (x, y))
            a.canvas = CANVAS
            a.draw()

        # Create Animals:
        for i in range(Prey_count):
            x = random.randrange(self.space.width)
            y = random.randrange(self.space.width)
            self.create_baby(x, y, age=random.randint(1, 5))
        for i in range(Tiger_count):
            x = random.randrange(self.space.width)
            y = random.randrange(self.space.width)
            self.create_baby(x, y, age=random.randint(1, 5), type='Tiger')

    def kill(self, a):
        if a.type == 'Prey':
            self.Prey_count -= 1
        else:
            self.Tiger_count -= 1
        x_1, y_1 = pos_box(a.pos)[:2]
        self.canvas.delete(a.icon)
        self.count -= 1
        self.space.remove_agent(a)
        self.schedule.remove(a)
        self.canvas.create_text(x_1, y_1, text="x", font=12, justify='center')

    def new_uid(self):
        '''Get a new uid and keep track of the last one'''
        uid = self.last_uid + 1
        self.last_uid = uid
        return uid

    def create_baby(self, x, y, age=0, type='Prey'):
        '''Create an animal and give it a ref to the CANVAS'''
        if type == 'Prey':
            a = Prey(self.new_uid(), self, age=age)
            self.Prey_count += 1
        else:
            a = Tiger(self.new_uid(), self, age=age)
            self.Tiger_count += 1
        self.schedule.add(a)
        self.space.place_agent(a, (x, y))
        self.count += 1
        a.canvas = self.canvas
        a.draw()

    def step(self):
        self.step_num += 1
        # print("Stepping:", self.step_num)

        # Regrow any grass that's due
        # Much faster than trying to call each individual grass cell as an agent every tick
        if self.step_num in self.grass_ticks:
            for grass in self.grass_ticks[self.step_num]:
                grass.regrow()
            del self.grass_ticks[self.step_num]

        # Move the agents
        self.schedule.step()

        if self.count <= 0:
            poem = f'''
            Simulation stopped at tick {self.step_num}
            No sun - no moon
            No morn - no noon
            No dawn - no dusk - no proper time of day
            No warmth, no cheerfulness, no healthful ease
            No comfortable feel in any member
            No shade, no shine, no butterflies, no bees
            No fruits, no flowers, no leaves, no birds
            November'''  # A poem by Thomas Hood
            for line in re.split('\n', poem):
                print(line)
                time.sleep(.1)


# #################################################################
# Main Graphics
CANVAS_MARGIN = 20
RESET_FLAG = False
RUNNING_FLAG = False


def repo_tkinter():
    '''Reposition tkinter objects assuming ROOT is the main window'''
    while True:
        time.sleep(0.1)
        root_x = ROOT.winfo_x()
        root_y = ROOT.winfo_y()
        mouse_x = ROOT.winfo_pointerx()
        mouse_y = ROOT.winfo_pointery()
        x = mouse_x - root_x
        y = mouse_y - root_y
        oid = str(ROOT.winfo_containing(mouse_x, mouse_y))[1:]

        if oid in ROOT.children:
            obj = ROOT.children[oid]
            w = obj.winfo_width()
            h = obj.winfo_height()
            obj.place(x=(x-w/2))
            obj.place(y=(y-h/2))
            # obj.config(text=', '.join(map(str,(x,y))))
            print(type(obj), oid, x, y)
            ROOT.update()


def repo(obj, x, y):
    '''Reposition objects'''
    print(type(obj), x, y, obj.winfo_width(), obj.winfo_height())
    obj.place(x=x)
    obj.place(y=y)


def reset():
    '''Reset button'''
    global RESET_FLAG
    global RUNNING_FLAG
    RESET_FLAG = True
    RUNNING_FLAG = False
    repo(CANVAS, -1024, -1024)


def run_simulation():
    '''Go button'''
    global RESET_FLAG
    global RUNNING_FLAG
    global NUM_TICKS
    global START_TIME
    global MAX_TICKS

    if RUNNING_FLAG:
        print('Already running')
        return
    else:
        RUNNING_FLAG = True

    START_TIME = time.time()

    num_ticks_str = NUM_TICKS_ENTRY.get()
    if not num_ticks_str.isdigit():
        print('Invalid input for number of ticks')
        return

    num_ticks = int(num_ticks_str)

    MAX_TICKS = num_ticks

    def update_progress(progress):
        PROGRESS_BAR["value"] = progress
        PROGRESS_LABEL["text"] = f"Progress: {progress}%"
        ROOT.update()
    def step():
        nonlocal num_ticks
        if RESET_FLAG or num_ticks <= 0:
            CANVAS.delete("all")
            CANVAS.config(background='grey')
            INFO_PREY.config(text="Prey:   ")
            INFO_TIGER.config(text="Tigers: ")
            elapsed_time = time.time() - START_TIME
            print("Total runtime:", str(datetime.timedelta(seconds=int(elapsed_time))))
            return

        model.step()
        if model.count == 0:
            return
        num_ticks -= 1
        INFO_PREY.config(text="Prey:   "+str(model.Prey_count))
        INFO_TIGER.config(text="Tigers: "+str(model.Tiger_count))

        # Calculate the progress percentage
        progress_percentage = int(((MAX_TICKS - num_ticks) / MAX_TICKS) * 100)
        print(progress_percentage)
        update_progress(progress_percentage)

        if NUM_TICKS > 0:
            ROOT.after(1, step)
        else:
            # Simulation completed, print total runtime
            elapsed_time = time.time() - start_time
            print("Total runtime:", str(datetime.timedelta(seconds=int(elapsed_time))))


    NUM_TICKS = num_ticks

    for s in OPTS.children.values():
        name = s.name
        val = s.get()
        globals()[name] = val
        print(name, val, globals()[name])

    repo(CANVAS, CANVAS_MARGIN, CANVAS_MARGIN+100)
    OPTS.lower()
    RESET_FLAG = False
    model = Prey_model(PREY_SLIDER.get(), TIGER_SLIDER.get(), 80, 80, CANVAS)
    ROOT.after(0, step)


ROOT = tk.Tk()
ROOT.title("Savannah")
ROOT.geometry('1024x1024')
INFO_PREY = tk.Label(ROOT, text="Prey:", justify='left')
repo(INFO_PREY, CANVAS_MARGIN, CANVAS_MARGIN)

INFO_PREY = tk.Label(ROOT, text="Prey:", justify='left')
repo(INFO_PREY, CANVAS_MARGIN, CANVAS_MARGIN)

PREY_SLIDER = tk.Scale(ROOT, from_=0, to=200, orient='horizontal', length=300)
repo(PREY_SLIDER, CANVAS_MARGIN+100, 0)
PREY_SLIDER.set(60)

INFO_TIGER = tk.Label(ROOT, text="Tigers:", justify='left')
repo(INFO_TIGER, CANVAS_MARGIN, CANVAS_MARGIN+40)

TIGER_SLIDER = tk.Scale(ROOT, from_=0, to=200, orient='horizontal', length=300)
repo(TIGER_SLIDER, CANVAS_MARGIN+100, CANVAS_MARGIN+20)
TIGER_SLIDER.set(10)

RESET_B = tk.Button(ROOT, text="Reset", command=reset, width=10)
repo(RESET_B, 450, CANVAS_MARGIN+40)

GO_B = tk.Button(ROOT, text="Go", command=run_simulation, width=10)
repo(GO_B, 450, CANVAS_MARGIN)

TICKS_LABEL = tk.Label(ROOT, text="Number of Ticks:", justify='left')
repo(TICKS_LABEL, 450, CANVAS_MARGIN)

NUM_TICKS_ENTRY = tk.Entry(ROOT, text="Number of Ticks", width=10)
repo(NUM_TICKS_ENTRY, 450 + GO_B.winfo_width() + 30, CANVAS_MARGIN)
NUM_TICKS_ENTRY.insert(0, str(NUM_TICKS))
repo(NUM_TICKS_ENTRY, 450 + GO_B.winfo_width() + 110, CANVAS_MARGIN)

repo(TICKS_LABEL, 560, CANVAS_MARGIN + 5)
repo(NUM_TICKS_ENTRY, 450 + GO_B.winfo_width() + 110, CANVAS_MARGIN + 30)

PROGRESS_BAR = ttk.Progressbar(ROOT, orient="horizontal", length=300, mode="determinate")
repo(PROGRESS_BAR, CANVAS_MARGIN, CANVAS_MARGIN + 80)

PROGRESS_LABEL = tk.Label(ROOT, text="Progress: 0%")
repo(PROGRESS_LABEL, CANVAS_MARGIN + 310, CANVAS_MARGIN + 80)


CANVAS = tk.Canvas(ROOT, width=830, height=830)
repo(CANVAS, CANVAS_MARGIN, CANVAS_MARGIN+100)

OPTS = tk.Frame(width=400, height=800)
repo(OPTS, CANVAS_MARGIN, CANVAS_MARGIN+100)

# List of user configurable variables and their labels:
GS = dict(
        ROCKY_AREAS="Percent of grass that is rocky.",
        AGE_T="How much to advance age each tick",
        GRASS_REGROW="Regrow grass every # years",
        FOOD_PER_TICK="Food consumed per tick",
        BABIES_PER_TIGER_PREGS="Babies per Tiger birth?",
        BABIES_PER_PREY_PREGS="Babies per Prey birth?",
        LIFESPAN_TIGER="Tiger lifespan",
        LIFESPAN_PREY="Prey lifespan",
        RADIUS_PREY="Prey food search radius",
        RADIUS_TIGER="Tiger food search radius",
        TICK_DELAY="Delay in ms after every tick",
        )


# Create sliders for user configurable variables
Y_POS = 0
for name, description in sorted(GS.items()):
    var = globals()[name]
    high = var*5
    resolution = high/100
    SLIDER = tk.Scale(OPTS, from_=0, to=high, orient='horizontal', length=300,
                      label=description, resolution=resolution, width=20)
    SLIDER.set(var)
    SLIDER.name = name
    repo(SLIDER, 0, Y_POS)
    Y_POS += 60


# Resize window to fit Canvas
ROOT.update()
WIDTH = CANVAS.winfo_x() + CANVAS.winfo_width() + CANVAS_MARGIN
HEIGHT = CANVAS.winfo_y() + CANVAS.winfo_height() + CANVAS_MARGIN
ROOT.geometry(str(WIDTH)+'x'+str(HEIGHT))

reset()
ROOT.mainloop()
