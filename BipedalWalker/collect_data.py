import gym
import numpy as np

from TD3 import TD3

#from TD3 import TD3
from PIL import Image
import os
import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
if not os.path.exists('data/'):
    os.mkdir('data/')
    
n_episodes = 100
env_name = "BipedalWalker-v3"
random_seed = 0
lr = 0.002
max_timesteps = 2000
render = True
save_gif = False
#filename = "TD3_{}_{}".format(env_name, random_seed)
#filename += '_solved'
filename = "TD3_BipedalWalker-v2_0_solved"
#directory = "./preTrained/{}".format(env_name)
directory = "./preTrained/BipedalWalker-v2/ONE"
env = gym.make(env_name, hardcore=False)
state_dim = env.observation_space.shape[0]
action_dim = env.action_space.shape[0]
max_action = float(env.action_space.high[0])
policy = TD3(lr, state_dim, action_dim, max_action)
policy.load_actor(directory, filename)


X_train = list()
A_train = list()
#obs_train = list()
states = list()
total_reward = 0

for ep in range(n_episodes):
    ep_reward = 0
    state = env.reset()
    for t in range(max_timesteps):
        #obs_train.append(state)
        
        img_array = env.render(mode='rgb_array')
        states.append(img_array)
  
        A, x = policy.select_action(state)
        state, reward, done, _ = env.step(A)
        #shape_x = len(x)#.size()
        X_train.append(x)
        A_train.append(A)
        ep_reward += reward        
        if done:
            break
        
    print('Episode: {}\tReward: {}'.format(ep, int(ep_reward)))
    #print("shape_state in X_train: ", shape_x)
    total_reward += ep_reward
    ep_reward = 0
env.close()        
               

print("Average Reward:", total_reward / n_episodes) 

X_train = np.array(X_train)
A_train = np.array(A_train)
#obs_train = np.array(obs_train)

obs_train = np.array(states)

np.save('data/X_train.npy', X_train)
np.save('data/a_train.npy', A_train)
np.save('data/obs_train.npy', obs_train)









