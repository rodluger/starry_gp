# -*- coding: utf-8 -*-
from ..base_op import BaseOp
from .tensordotRz_rev import tensordotRzRevOp
from theano import gof
import theano
import theano.tensor as tt

__all__ = ["tensordotRzOp"]


class tensordotRzOp(BaseOp):
    func_file = "./tensordotRz.cc"
    func_name = "APPLY_SPECIFIC(tensordotRz)"

    def __init__(self, *args, **kwargs):
        self.grad_op = tensordotRzRevOp(*args, **kwargs)
        super().__init__(*args, **kwargs)

    def make_node(self, M, theta):
        in_args = []
        dtype = theano.config.floatX
        for a in [M, theta]:
            try:
                a = tt.as_tensor_variable(a)
            except tt.AsTensorError:
                pass
            else:
                dtype = theano.scalar.upcast(dtype, a.dtype)
            in_args.append(a)
        out_args = [
            tt.TensorType(dtype=dtype, broadcastable=[False, False])(),
        ]
        return gof.Apply(self, in_args, out_args)

    def infer_shape(self, node, shapes):
        K = shapes[0][0]
        return ([K, self.N],)

    def grad(self, inputs, gradients):
        return self.grad_op(*inputs, gradients[0])

    def R_op(self, inputs, eval_points):
        if eval_points[0] is None:
            return eval_points
        return self.grad(inputs, eval_points)
