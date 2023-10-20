import torch
from typing import NamedTuple
from utils.boolmask import mask_long2bool, mask_long_scatter


class StateLSCP(NamedTuple):
    # Fixed input
    loc: torch.Tensor
    dist: torch.Tensor

    # If this state contains multiple copies (i.e. beam search) for the same instance, then for memory efficiency
    # the loc and dist tensors are not kept multiple times, so we need to use the ids to   index the correct rows.
    ids: torch.Tensor  # Keeps track of original fixed data index of rows

    # State
    first_a: torch.Tensor
    prev_a: torch.Tensor
    visited_: torch.Tensor  # Keeps track of nodes that have been visited
    # mask_cover
    mask_cover: torch.Tensor
    theta: torch.Tensor
    radius: torch.Tensor
    dynamic: torch.Tensor
    dynamic_updation: torch.Tensor

    # lengths: torch.Tensor
    cover_num: torch.Tensor
    cur_coord: torch.Tensor
    i: torch.Tensor  # Keeps track of step

    @property
    def visited(self):
        if self.visited_.dtype == torch.bool:
            return self.visited_
        else:
            return mask_long2bool(self.visited_, n=self.loc.size(-2))

    def __getitem__(self, key):
        if torch.is_tensor(key) or isinstance(key, slice):  # If tensor, idx all tensors by this tensor:
            return self._replace(
                ids=self.ids[key],
                first_a=self.first_a[key],
                prev_a=self.prev_a[key],
                visited_=self.visited_[key],
                mask_cover=self.mask_cover[key],
                dynamic=self.dynamic[key],
                dynamic_updation=self.dynamic_updation[key],
                cover_num = self.cover_num[key],
                # lengths=self.lengths[key],
                cur_coord=self.cur_coord[key] if self.cur_coord is not None else None,
            )
        return super(StateLSCP, self).__getitem__(key)

    @staticmethod
    def initialize(input, visited_dtype=torch.bool):
        loc = input['loc']
        theta = input['theta']
        radius = input['radius']
        batch_size, n_loc, _ = loc.size()
        prev_a = torch.zeros(batch_size, 1, dtype=torch.long, device=loc.device)

        return StateLSCP(
            loc=loc,
            dist=(loc[:, :, None, :] - loc[:, None, :, :]).norm(p=2, dim=-1),
            ids=torch.arange(batch_size, dtype=torch.int64, device=loc.device)[:, None],  # Add steps dimension
            first_a=prev_a,
            prev_a=prev_a,
            # Keep visited with depot so we can scatter efficiently (if there is an action for depot)
            visited_=(  # Visited as mask is easier to understand, as long more memory efficient
                torch.zeros(
                    batch_size, 1, n_loc,
                    dtype=torch.bool, device=loc.device
                )
                if visited_dtype == torch.bool
                else torch.zeros(batch_size, 1, (n_loc + 63) // 64, dtype=torch.int64, device=loc.device)  # Ceil
            ),
            mask_cover=(  # Visited as mask is easier to understand, as long more memory efficient
                torch.zeros(
                    batch_size, 1, n_loc,
                    dtype=torch.bool, device=loc.device
                )
                if visited_dtype == torch.bool
                else torch.zeros(batch_size, 1, (n_loc + 63) // 64, dtype=torch.int64, device=loc.device)  # Ceil
            ),
            theta = theta[0].type(torch.float),
            radius = radius[0].type(torch.float),
            # radius=radius[0],
            dynamic=torch.ones(batch_size, 1, n_loc, dtype=torch.float, device=loc.device),
            dynamic_updation=torch.arange(radius[0], device=loc.device).float().expand(batch_size, 1, -1) /
                             radius[0],
            # cover_num=torch.zeros(batch_size, 1, dtype=torch.float64, device=loc.device),
            cover_num=torch.zeros(batch_size, 1, device=loc.device),
            # lengths=torch.zeros(batch_size, 1, device=loc.device),
            cur_coord=None,
            i=torch.zeros(1, dtype=torch.int64, device=loc.device)  # Vector with length num_steps
        )

    def get_final_cost(self):

        assert self.all_finished()
        # assert self.visited_.
        site_num = self.cover_num
        return site_num

    def update(self, selected):

        # Update the state
        prev_a = selected[:, None]  # Add dimension for step

        cur_coord = self.loc[self.ids, prev_a]
        cover_num = self.cover_num
        # if self.cur_coord is not None:  # Don't add length for first action (selection of start node)
        #     lengths = self.lengths + (cur_coord - self.cur_coord).norm(p=2, dim=-1)  # (batch_dim, 1)

        # Update should only be called with just 1 parallel step, in which case we can check this way if we should update
        first_a = prev_a if self.i.item() == 0 else self.first_a

        if self.visited_.dtype == torch.bool:
            # Add one dimension since we write a single value
            visited_ = self.visited_.scatter(-1, prev_a[:, :, None], 1)
        else:
            visited_ = mask_long_scatter(self.visited_, prev_a)

        # mask covered cities
        batch_size, sequence_size, _ = self.loc.size()
        batch_size = self.ids.size(0)
        dists = (self.loc[self.ids.squeeze(-1)]-cur_coord).norm(p=2, dim=-1)
        # nearest_idx = torch.where(dists[0, :] < self.radius)[0].view(1, -1).expand(batch_size, -1)
        # dists.argsort()[np.sort(dists) < 0.1] dists.argsort()[torch.sort(dists)[0]<0.15]

        mask_cover = self.mask_cover.clone()
        dynamic = self.dynamic.clone()

        for i in range(batch_size):
            if len(self.radius.size()) == 0:
                n_idx = dists[i].argsort()[torch.sort(dists[i])[0] < self.radius]
            else:
                n_idx = dists[i].argsort()[torch.sort(dists[i])[0] < self.radius.squeeze(0)[selected[i]]]

            mask_cover[i, 0, n_idx] = 1
            # dynamic[i, 0, n_idx[0]] = 0
            dynamic[i, 0, n_idx] = 0

            cover_num[i] = mask_cover[i, 0].sum()
            if len(n_idx)>1:
                n_idx = n_idx[1:]
            dynamic_updation = torch.arange(n_idx.size(0), device=self.dynamic.device)\
                                   .float() / n_idx.size(0)
            dynamic[i, 0, n_idx] = dynamic[i, 0, n_idx].mul(dynamic_updation)

        return self._replace(first_a=first_a, prev_a=prev_a, visited_=visited_, mask_cover=mask_cover,dynamic=dynamic,
                             cover_num=cover_num, cur_coord=cur_coord, i=self.i + 1)

    def all_finished(self):
        # Exactly n steps
        return (self.cover_num >=self.theta * self.mask_cover.size(-1)).all()
        # return (self.mask_cover.sum(-1) >= self.theta * self.mask_cover.size(-1)).all()

        # return self.mask_cover.all()

    def get_finished(self):
        return (self.cover_num >= self.theta * self.mask_cover.size(-1))
        # return (self.mask_cover.sum(-1) == self.mask_cover.size(-1))

    def get_current_node(self):
        return self.prev_a

    def get_dynamic(self):
        return self.dynamic

    def get_mask(self):
        return self.visited

    def get_nn(self, k=None):
        # Insert step dimension
        # Nodes already visited get inf so they do not make it
        if k is None:
            k = self.loc.size(-2) - self.i.item()  # Number of remaining
        return (self.dist[self.ids, :, :] + self.visited.float()[:, :, None, :] * 1e6).topk(k, dim=-1, largest=False)[1]

    def get_nn_current(self, k=None):
        assert False, "Currently not implemented, look into which neighbours to use in step 0?"
        # Note: if this is called in step 0, it will have k nearest neighbours to node 0, which may not be desired
        # so it is probably better to use k = None in the first iteration
        if k is None:
            k = self.loc.size(-2)
        k = min(k, self.loc.size(-2) - self.i.item())  # Number of remaining
        return (
            self.dist[
                self.ids,
                self.prev_a
            ] +
            self.visited.float() * 1e6
        ).topk(k, dim=-1, largest=False)[1]

    def construct_solutions(self, actions):
        return actions
