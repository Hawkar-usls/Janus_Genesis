from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional
import torch
import torch.nn as nn
import torch.nn.functional as F

@dataclass(frozen=True)
class JanusModelConfig:
    vocab_size:int=258; context_length:int=128; d_model:int=128; n_heads:int=4; n_layers:int=2; ff_mult:int=4; dropout:float=0.10
    def to_dict(self): return asdict(self)
    @classmethod
    def from_dict(cls,obj): return cls(**obj)

class ByteTokenizer:
    BOS=256; EOS=257; vocab_size=258
    @classmethod
    def encode(cls,text,bos=False,eos=False):
        ids=list(text.encode('utf-8',errors='replace'))
        if bos: ids.insert(0,cls.BOS)
        if eos: ids.append(cls.EOS)
        return ids
    @classmethod
    def decode(cls,ids):
        return bytes(i for i in ids if 0 <= int(i) < 256).decode('utf-8',errors='replace')

class JanusTinyTransformer(nn.Module):
    def __init__(self,config):
        super().__init__(); self.config=config
        if config.d_model % config.n_heads: raise ValueError('d_model must be divisible by n_heads')
        self.token=nn.Embedding(config.vocab_size,config.d_model)
        self.pos=nn.Embedding(config.context_length,config.d_model)
        layer=nn.TransformerEncoderLayer(d_model=config.d_model,nhead=config.n_heads,dim_feedforward=config.d_model*config.ff_mult,dropout=config.dropout,activation='gelu',batch_first=True,norm_first=True)
        self.blocks=nn.TransformerEncoder(layer,num_layers=config.n_layers)
        self.norm=nn.LayerNorm(config.d_model)
        self.lm_head=nn.Linear(config.d_model,config.vocab_size,bias=False); self.lm_head.weight=self.token.weight
        self.apply(self._init_weights)
    @staticmethod
    def _init_weights(module):
        if isinstance(module,(nn.Linear,nn.Embedding)):
            nn.init.normal_(module.weight,mean=0.0,std=0.02)
            if isinstance(module,nn.Linear) and module.bias is not None: nn.init.zeros_(module.bias)
    def forward(self,idx,targets:Optional[torch.Tensor]=None):
        if idx.ndim != 2: raise ValueError('idx must have shape [batch, time]')
        _,t=idx.shape
        if t>self.config.context_length:
            idx=idx[:,-self.config.context_length:]
            if targets is not None: targets=targets[:,-self.config.context_length:]
            t=idx.shape[1]
        positions=torch.arange(t,device=idx.device)
        x=self.token(idx)+self.pos(positions)[None,:,:]
        causal=torch.full((t,t),float('-inf'),device=idx.device); causal=torch.triu(causal,diagonal=1)
        x=self.blocks(x,mask=causal); logits=self.lm_head(self.norm(x)); loss=None
        if targets is not None: loss=F.cross_entropy(logits.reshape(-1,logits.size(-1)),targets.reshape(-1))
        return logits,loss
    @torch.no_grad()
    def generate(self,idx,max_new_tokens=160,temperature=0.8,top_k=40):
        self.eval()
        for _ in range(max_new_tokens):
            x=idx[:,-self.config.context_length:]; logits,_=self(x); logits=logits[:,-1,:]/max(0.05,float(temperature))
            if top_k>0:
                v,_=torch.topk(logits,min(top_k,logits.size(-1))); logits=torch.where(logits<v[:,[-1]],torch.full_like(logits,float('-inf')),logits)
            probs=torch.softmax(logits,dim=-1); nxt=torch.multinomial(probs,1); idx=torch.cat([idx,nxt],dim=1)
            if int(nxt.item())==ByteTokenizer.EOS: break
        return idx

def parameter_count(model): return sum(p.numel() for p in model.parameters())
