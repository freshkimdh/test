import torch
import torch.nn as nn 
import torchvision 
from torchvision import transforms
from torchvision import datasets
from torch.utils.data import DataLoader
from torchvision.utils import save_image
import tqdm

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(device)

# Networks G & D
class conditional_G(nn.Module):
    def __init__(self, z_dim, img_size):
        super().__init__()
        self.img_size = img_size
        self.G = nn.Sequential(
            nn.Linear(in_features=z_dim*2, out_features=256),
            nn.ReLU(),
            nn.Linear(in_features=256, out_features=256),
            nn.ReLU(),
            nn.Linear(in_features=256, out_features=self.img_size * self.img_size),
            nn.Tanh()
        )
        
    def forward(self, x, c): 
        batch_size = x.shape[0] 
        c = c.unsqueeze(1).expand(x.size())
        x = torch.cat((x, c), dim=1)
        out = self.G(x)
        out = out.view(batch_size, 1, self.img_size, self.img_size)
        return out 

class conditional_D(nn.Module):
    def __init__(self, img_size):
        super().__init__()
        self.img_size = img_size
        self.D = nn.Sequential(
            nn.Linear(in_features=self.img_size * self.img_size * 2, out_features=256),
            nn.LeakyReLU(negative_slope=0.2),
            nn.Linear(in_features=256, out_features=256),
            nn.LeakyReLU(negative_slope=0.2),
            nn.Linear(in_features=256, out_features=1),
            nn.Sigmoid(),
        )

    def forward(self, x, c): 
        batch_size = x.shape[0] 
        out = x.view(batch_size, -1)
        # print("C out size1 : ",c.shape)
        # print("D out size : ",out.shape)
        c = c.unsqueeze(1).expand(out.size())
        # print("c out size2 : ",c.shape)
        out = torch.cat((out, c), dim=1)
        # print("out size : ",out.shape)
        out = self.D(out) # [batch, 1]
        return out 

class G_Loss(nn.Module):
    def __init__(self, device):
        super(G_Loss, self).__init__()
        self.device = device 
        self.criterion = nn.BCELoss()

    def forward(self, fake):
        ones = torch.ones_like(fake).to(self.device)

        g_loss = self.criterion(fake, ones)

        return g_loss

class D_Loss(nn.Module):
    def __init__(self, device):
        super(D_Loss, self).__init__()
        self.device = device
        self.criterion = nn.BCELoss()

    def forward(self, D_real, D_fake):
        ones = torch.ones_like(D_real).to(self.device)
        zeros = torch.zeros_like(D_fake).to(self.device)

        d_real_loss = self.criterion(D_real, ones)
        d_fake_loss = self.criterion(D_fake, zeros)

        d_loss = d_real_loss + d_fake_loss

        return d_loss, d_real_loss, d_fake_loss

G_ckpt_folder = 'G_ckpt' 
D_ckpt_folder = 'D_ckpt' 
fake_img_folder = 'fake_images'

# Hyper-parameters 
num_epochs = 40
batch_size = 100
img_size = 28
save_step_interval = 300

# 모델 Hyper-parameters
z_dim = 100 
lr_G = 0.0002
lr_D = 0.0002
beta1 = 0.5 
beta2 = 0.999

# dataset & loader 
transform = transforms.Compose([transforms.ToTensor(),
                                transforms.Normalize(mean=0.5, std=0.5)])

mnist_dataset = datasets.MNIST(root='./data', train=True, 
                               transform=transform, download=True)

mnist_loader = DataLoader(dataset=mnist_dataset, 
                          batch_size=batch_size, 
                          shuffle=True)

def to_img(x): 
    return torch.clamp((x+1)/2, 0, 1)


G = conditional_G(z_dim, img_size).to(device)
D = conditional_D(img_size).to(device)

# Loss 
G_loss = G_Loss(device)
D_loss = D_Loss(device)

# optimizer 
G_optim = torch.optim.Adam(G.parameters(), lr=lr_G, betas=(beta1, beta2))
D_optim = torch.optim.Adam(D.parameters(), lr=lr_D, betas=(beta1, beta2))


# 이미지 생성에 사용할 고정 label과 random number
eval_c = torch.tensor([0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9], 
                      dtype=torch.float32).to(device)
eval_z = torch.randn(eval_c.shape[0], z_dim).to(device)

# Train
for epoch in tqdm.tqdm(range(num_epochs)): 
    for i, (images, labels) in enumerate(mnist_loader):
        G.train()
        D.train()
        images = images.to(device)
        labels = labels.to(device)

        ### update D ### 
        z = torch.randn(batch_size, z_dim).to(device)
        fake_images = G(z, labels)

        D_real = D(images, labels)
        D_fake = D(fake_images.detach(), labels)

        d_loss, d_real_loss, d_fake_loss = D_loss(D_real, D_fake)

        D_optim.zero_grad()
        d_loss.backward()
        D_optim.step()

        ### update G ### 
        z = torch.randn(batch_size, z_dim).to(device)
        fake_images = G(z, labels)

        G_fake = D(fake_images, labels)

        g_loss = G_loss(G_fake)

        G_optim.zero_grad()
        g_loss.backward()
        G_optim.step()

        ### save middle ckpt and fake img ### 
        if i % save_step_interval == 0 : 
            with torch.no_grad():
                save_name = f'{str(epoch+1).zfill(3)}_{str(i).zfill(3)}'
                G.eval()
                D.eval()
                torch.save(G.state_dict(), f'{G_ckpt_folder}/G_model_{save_name}.ckpt')
                torch.save(D.state_dict(), f'{D_ckpt_folder}/D_model_{save_name}.ckpt')
                
                fake_images = G(eval_z, eval_c)
                save_image(to_img(fake_images), 
                           f'{fake_img_folder}/gen_imgs_{save_name}.jpg')

    print(f'EPOCH {epoch+1} LOSS value G : {g_loss:.4f} / D(r, f) : {d_loss:.4f} ({d_real_loss:.4f} , {d_fake_loss:.4f})')