import gym
import numpy as np
import torch
import torch.nn as nn
import numpy as np      
#import pandas as pd
import pickle

from copy import deepcopy
from torch.utils.data import TensorDataset, DataLoader
from argparse import ArgumentParser
from os.path import join

from torch.utils.tensorboard import SummaryWriter
import os 

from TD3 import TD3
from PIL import Image

from sklearn.decomposition import PCA
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neighbors import KNeighborsRegressor
from sklearn.metrics import silhouette_score
from sklearn.cluster import KMeans, DBSCAN, OPTICS

from random import sample
from tqdm import tqdm
from time import sleep
from sklearn.cluster import KMeans
from sklearn.metrics import mean_absolute_error

from random import sample
from tqdm import tqdm
from time import sleep
from collections import Counter

NUM_ITERATIONS = 15
NUM_EPOCHS = 100
NUM_CLASSES = 4
NUM_PROTOTYPES = 8

LATENT_SIZE = 300
BATCH_SIZE = 64
DEVICE = 'cpu'
PROTOTYPE_SIZE = 50
MAX_SAMPLES = 100000
delay_ms = 0
SIMULATION_EPOCHS = 10 #30

env_name = "BipedalWalker-v3"
random_seed = 0
n_episodes = 30
lr = 0.002
max_timesteps = 2000
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


class PPNet(nn.Module):

    def __init__(self):
        super(PPNet, self).__init__()
        self.main = nn.Sequential(
            nn.Linear(LATENT_SIZE, PROTOTYPE_SIZE),
            nn.BatchNorm1d(PROTOTYPE_SIZE),
            nn.ReLU(),
            nn.Linear(PROTOTYPE_SIZE, PROTOTYPE_SIZE),
        )
        self.prototypes = nn.Parameter( torch.randn( (NUM_PROTOTYPES, PROTOTYPE_SIZE), dtype=torch.float32), requires_grad=True)
        self.epsilon = 1e-5
        self.linear = nn.Linear(NUM_PROTOTYPES, NUM_CLASSES, bias=False) 
        self.__make_linear_weights()
        self.tanh = nn.Tanh()
        
    def __make_linear_weights(self):
        custom_weight_matrix = torch.tensor([
                                             [ 1., 0., 0., 0.], 
                                             [ -1., 0., 0., 0.], 
                                             [ 0., 1., 0., 0.], 
                                             [ 0., -1., 0., 0.], 
                                             [ 0., 0., 1., 0.],
                                             [ 0., 0., -1., 0.], 
                                             [ 0., 0., 0., 1.], 
                                             [ 0., 0., 0., -1.], 
                                             ])
        self.linear.weight.data.copy_(custom_weight_matrix.T)   
        
    def __proto_layer_l2(self, x):
        output = list()
        b_size = x.shape[0]
        p = self.prototypes.T.view(1, PROTOTYPE_SIZE, NUM_PROTOTYPES).tile(b_size, 1, 1).to(DEVICE) 
        c = x.view(b_size, PROTOTYPE_SIZE, 1).tile(1, 1, NUM_PROTOTYPES).to(DEVICE)            
        l2s = ( (c - p)**2 ).sum(axis=1).to(DEVICE) 
        act = torch.log( (l2s + 1. ) / (l2s + self.epsilon) ).to(DEVICE)   
        return act, l2s
    
    def __output_act_func(self, p_acts):        
        return self.tanh(p_acts)
    
    def forward(self, x): 
        x = self.main(x)
        p_acts, l2s = self.__proto_layer_l2(x)
        logits = self.linear(p_acts)
        final_outputs = self.__output_act_func(logits)
        return final_outputs, x


def evaluate_loader(model, loader, mse_loss):
    model.eval()
    total_loss = 0
    total = 0
    
    with torch.no_grad():
        for i, data in enumerate(loader):
            imgs, labels = data
            imgs, labels = imgs.to(DEVICE), labels.to(DEVICE)
            outputs, _ = model(imgs)
            loss = mse_loss(outputs, labels)
            total += len(outputs)
            total_loss += loss.item()
    model.train()
    return total_loss / len(loader)



def trans_human_concepts(model, nn_human_x):
    model.eval()
    trans_nn_human_x = list()
    for i, t in enumerate(model.ts):
        trans_nn_human_x.append( t( torch.tensor(nn_human_x[i], dtype=torch.float32).view(1, -1)) )
    model.train()
    return torch.cat(trans_nn_human_x, dim=0)


def clust_loss(x, y, model, criterion):
    """
    Forces each prototype to be close to training data
    """
    
    ps = model.prototypes  # take prototypes in new feature space
    model = model.eval()
    x = model.main(instances)  # transform into new feature space
    b_size = x.shape[0]
    for idx, p in enumerate(ps):
        target = p.repeat(b_size, 1)
        if idx == 0:
            loss = criterion(x, target) 
        else:
            loss += criterion(x, target)
    model = model.train()  
    return loss


def sep_loss(x, y, model, criterion):
    """
    Force each prototype to be far from eachother
    """
    
    p = model.prototypes  # take prototypes in new feature space
    model = model.eval()
    x = model.main(x)  # transform into new feature space
    loss = torch.cdist(p, p).sum() / ((NUM_PROTOTYPES**2 - NUM_PROTOTYPES) / 2)
    return -loss 


if not os.path.exists('results/'):
    os.makedirs('results/')

with open('results/pwnet_star_results.txt', 'a') as f:
    f.write("--------------------------------------------------------------------------------------------------------------------------\n")
    f.write(f"model_pwnet_star\n")
    f.write(f"NUM_PROTOTYPES: {NUM_PROTOTYPES}\n")

#### Start Collecting Data To Form Final Mean and Standard Error Results

MODEL_DIR = 'weights/pwnet_star'
if not os.path.exists(MODEL_DIR):
    os.makedirs(MODEL_DIR)
    
data_rewards = list()
data_errors = list()

for iter in range(NUM_ITERATIONS):
    
    with open('results/pwnet_star_results.txt', 'a') as f:
        f.write(f"ITERATION {iter}: \n")

    MODEL_DIR_ITER = f'weights/pwnet_star/iter_{iter}.pth'

    prototype_path = f'prototypes/pwnet_star/iter_{iter}/'
    if not os.path.exists(prototype_path):
        os.makedirs(prototype_path)
                
    writer = SummaryWriter(f"runs/pwnet_star/Iteration_{iter}")
    
    X_train = np.load('data/X_train.npy')
    a_train = np.load('data/a_train.npy')
    obs_train = np.load('data/obs_train.npy')
    
    tensor_x = torch.Tensor(X_train)
    tensor_y = torch.tensor(a_train, dtype=torch.float32)
    train_dataset = TensorDataset(tensor_x, tensor_y)
    train_loader = DataLoader(train_dataset, shuffle=True, batch_size=BATCH_SIZE)

    #### Train Wrapper
    model = PPNet().eval()
    model.to(DEVICE)
    mse_loss = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=1e-8)
    scheduler = torch.optim.lr_scheduler.ExponentialLR(optimizer, gamma=0.95)
    best_error = np.float64('inf')
    model.train()

    # Freeze Linear Layer to make more interpretable
    model.linear.weight.requires_grad = False

    # Could tweak these, haven't tried
    lambda1 = 1.0
    lambda2 = 0.08
    lambda3 = 0.008

    running_loss = 0.
    for epoch in range(NUM_EPOCHS):
        running_loss1 = 0
        running_loss2 = 0
        running_loss3 = 0
        model.eval()
        train_error = evaluate_loader(model, train_loader, mse_loss)
        model.train()

        if train_error < best_error:
            torch.save(model.state_dict(), MODEL_DIR_ITER)
            best_error = train_error

        for instances, labels in train_loader:
            optimizer.zero_grad()
            instances, labels = instances.to(DEVICE), labels.to(DEVICE)
            logits, _ = model(instances)
            loss1 = mse_loss(logits, labels) * lambda1
            loss2 = clust_loss(instances, labels, model, mse_loss) * lambda2
            loss3 = sep_loss(instances, labels, model, mse_loss) * lambda3
            loss  = loss1 + loss2 + loss3
            running_loss += loss.item()

            loss.backward()
            optimizer.step()
            
        print("Epoch:", epoch, "Loss:", running_loss / len(train_loader), "Train_error:", train_error)
        with open('results/pwnet_star_results.txt', 'a') as f:
            f.write(f"Epoch: {epoch}, Loss: {running_loss / len(train_loader)}, Train_error: {train_error}\n")
        
        writer.add_scalar("Running_loss", running_loss/len(train_loader), epoch)
        writer.add_scalar("Train_error", train_error, epoch)

        scheduler.step()  
                   
    # Project to training data
    model = PPNet().eval()
    model.load_state_dict(torch.load(MODEL_DIR_ITER))
    trans_x = list()
    model.eval()
    with torch.no_grad():
        for i in tqdm(range(len(X_train))):
            img = X_train[i]
            _, x = model(  torch.tensor(img, dtype=torch.float32).view(1, -1)  )
            trans_x.append(x[0].tolist())
    trans_x = np.array(trans_x)

    nn_xs = list()
    nn_as = list()
    nn_human_images = list()
    for i in range(NUM_PROTOTYPES):
        trained_prototype = model.prototypes.clone().detach()[i].view(1,-1)
        knn = KNeighborsRegressor(algorithm='brute')
        knn.fit(trans_x, list(range(len(trans_x))))
        dist, nn_idx = knn.kneighbors(X=trained_prototype, n_neighbors=1, return_distance=True)
        nn_x = trans_x[nn_idx.item()]    
        nn_xs.append(nn_x.tolist())
        
        print("I'm saving prototypes' images in prototypes/ directory...")
        prototype_image = obs_train[nn_idx.item()]
        prototype_image = Image.fromarray(prototype_image, 'RGB')
        p_path = prototype_path+f'p{i+1}.png'
        prototype_image.save(p_path)
        
    trained_prototypes = model.prototypes.clone().detach()
    model.prototypes = torch.nn.Parameter(  torch.tensor(nn_xs, dtype=torch.float32)  )
    torch.save(model.state_dict(), MODEL_DIR_ITER)

    # Simulation
    total_reward = list()
    all_errors = list()
    model.eval()

    for ep in range(SIMULATION_EPOCHS):
        ep_reward = 0
        ep_errors = 0
        state = env.reset()
        for t in range(max_timesteps):
            bb_action, x = policy.select_action(state)
            A, _ = model( torch.tensor(x, dtype=torch.float32).view(1, -1) )
            state, reward, done, _ = env.step(A.detach().numpy()[0])
            ep_reward += reward
            ep_errors += mse_loss( torch.tensor(bb_action), A[0]).detach().item()

            if done:
                break

        print('Episode: {}\tReward: {}'.format(ep, int(ep_reward)))
        total_reward.append( ep_reward )
        all_errors.append( ep_errors )
        ep_reward = 0
    env.close()  
    data_rewards.append( sum(total_reward) / SIMULATION_EPOCHS )      
    data_errors.append( sum(all_errors) / SIMULATION_EPOCHS )    
  
    data_rewards.append(  sum(total_reward) / SIMULATION_EPOCHS  )
    data_errors.append(  sum(all_errors) / SIMULATION_EPOCHS )
    print("Reward: ", sum(total_reward) / SIMULATION_EPOCHS)
    print("MSE: ", sum(all_errors) / SIMULATION_EPOCHS )
    
    # log the reward and MAE
    writer.add_scalar("Reward", sum(total_reward) / SIMULATION_EPOCHS, iter)
    writer.add_scalar("MSE", sum(all_errors) / SIMULATION_EPOCHS, iter)
    
    with open('results/pwnet_star_results.txt', 'a') as f:
        f.write(f"Reward: {sum(total_reward) / SIMULATION_EPOCHS}, MSE: {sum(all_errors) / SIMULATION_EPOCHS}\n")

data_errors = np.array(data_errors)
data_rewards = np.array(data_rewards)


print(" ")
print("===== Data MAE:")
print("MSE:", data_errors)
print("Mean:", data_errors.mean())
print("Standard Error:", data_errors.std() / np.sqrt(NUM_ITERATIONS)  )
print(" ")
print("===== Data Reward:")
print("Rewards:", data_rewards)
print("Mean:", data_rewards.mean())
print("Standard Error:", data_rewards.std() / np.sqrt(NUM_ITERATIONS)  )

with open('results/pwnet_star_results.txt', 'a') as f:
    f.write("\n===== Data MAE:\n")
    f.write(f"MSE:  {data_errors}\n")
    f.write(f"Mean: {data_errors.mean()}\n")
    f.write(f"Standard Error: {data_errors.std() / np.sqrt(NUM_ITERATIONS)}\n")
    f.write("\n===== Data Reward:\n")
    f.write(f"Rewards:  {data_rewards}\n")
    f.write(f"Mean: {data_rewards.mean()}\n")
    f.write(f"Standard Error: {data_rewards.std() / np.sqrt(NUM_ITERATIONS)}\n")













