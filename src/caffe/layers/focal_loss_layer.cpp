#include <algorithm>
#include <cfloat>
#include <vector>

#include "caffe/layers/focal_loss_layer.hpp"
#include "caffe/util/math_functions.hpp"

namespace caffe {

template <typename Dtype>
void focalSoftmaxWithLossLayer<Dtype>::LayerSetUp(
    const vector<Blob<Dtype>*>& bottom, const vector<Blob<Dtype>*>& top) {
  LossLayer<Dtype>::LayerSetUp(bottom, top);
  LayerParameter softmax_param(this->layer_param_);
  softmax_param.set_type("Softmax");
  softmax_layer_ = LayerRegistry<Dtype>::CreateLayer(softmax_param);
  softmax_bottom_vec_.clear();
  softmax_bottom_vec_.push_back(bottom[0]);
  softmax_top_vec_.clear();
  softmax_top_vec_.push_back(&prob_);
  softmax_layer_->SetUp(softmax_bottom_vec_, softmax_top_vec_);

  has_ignore_label_ =
    this->layer_param_.loss_param().has_ignore_label();
  if (has_ignore_label_) {
    ignore_label_ = this->layer_param_.loss_param().ignore_label();
  }
  if (!this->layer_param_.loss_param().has_normalization() &&
      this->layer_param_.loss_param().has_normalize()) {
    normalization_ = this->layer_param_.loss_param().normalize() ?
                     LossParameter_NormalizationMode_VALID :
                     LossParameter_NormalizationMode_BATCH_SIZE;
  } else {
    normalization_ = this->layer_param_.loss_param().normalization();
  }
  alpha_ = 0.75;
  gamma_ = 2.0f;
}

template <typename Dtype>
void focalSoftmaxWithLossLayer<Dtype>::Reshape(
    const vector<Blob<Dtype>*>& bottom, const vector<Blob<Dtype>*>& top) {
  LossLayer<Dtype>::Reshape(bottom, top);
  softmax_layer_->Reshape(softmax_bottom_vec_, softmax_top_vec_);
  softmax_axis_ =
      bottom[0]->CanonicalAxisIndex(this->layer_param_.softmax_param().axis());
  outer_num_ = bottom[0]->count(0, softmax_axis_);
  inner_num_ = bottom[0]->count(softmax_axis_ + 1);
  CHECK_EQ(outer_num_ * inner_num_, bottom[1]->count())
      << "Number of labels must match number of predictions; "
      << "e.g., if softmax axis == 1 and prediction shape is (N, C, H, W), "
      << "label count (number of labels) must be N*H*W, "
      << "with integer values in {0, 1, ..., C-1}.";
  if (top.size() >= 2) {
    // softmax output
    top[1]->ReshapeLike(*bottom[0]);
  }
}

template <typename Dtype>
void focalSoftmaxWithLossLayer<Dtype>::Forward_cpu(
    const vector<Blob<Dtype>*>& bottom, const vector<Blob<Dtype>*>& top) {
  // The forward pass computes the softmax prob values.
  softmax_layer_->Forward(softmax_bottom_vec_, softmax_top_vec_);
  const Dtype* prob_data = prob_.cpu_data();
  const Dtype* label = bottom[1]->cpu_data();
  int dim = prob_.count() / outer_num_;
  int count = 0;
  Dtype loss = 0;
  //Dtype negloss=0, posloss=0;
  for (int i = 0; i < outer_num_; ++i) {
    for (int j = 0; j < inner_num_; j++) {
      const int label_value = static_cast<int>(label[i * inner_num_ + j]);
      if (has_ignore_label_ && label_value == ignore_label_) {
        continue;
      }
      DCHECK_GE(label_value, 0);
      DCHECK_LT(label_value, prob_.shape(softmax_axis_));
      Dtype prob_a = prob_data[i * dim + label_value * inner_num_ + j];
      loss -= log(std::max(prob_a,
                           Dtype(FLT_MIN)))*std::pow(1 -prob_a, gamma_)*alpha_;
      ++count;
    }
  }
  Dtype normalizer = LossLayer<Dtype>::GetNormalizer(
      normalization_, outer_num_, inner_num_, count);
  top[0]->mutable_cpu_data()[0] = loss / normalizer;
  if (top.size() == 2) {
    top[1]->ShareData(prob_);
  }
}

template <typename Dtype>
void focalSoftmaxWithLossLayer<Dtype>::Backward_cpu(const vector<Blob<Dtype>*>& top,
    const vector<bool>& propagate_down, const vector<Blob<Dtype>*>& bottom) {
  if (propagate_down[1]) {
    LOG(FATAL) << this->type()
               << " Layer cannot backpropagate to label inputs.";
  }
  if (propagate_down[0]) {
    Dtype* bottom_diff = bottom[0]->mutable_cpu_diff();
    const Dtype* prob_data = prob_.cpu_data();
    const Dtype* label = bottom[1]->cpu_data();
    int dim = prob_.count() / outer_num_;
    int count = 0;
    Dtype focaldiff = 0;
    for (int i = 0; i < outer_num_; ++i) {
      for (int j = 0; j < inner_num_; ++j) {
        const int label_value = static_cast<int>(label[i * inner_num_ + j]);
        if (has_ignore_label_ && label_value == ignore_label_) {
          for (int c = 0; c < bottom[0]->shape(softmax_axis_); ++c) {
            bottom_diff[i * dim + c * inner_num_ + j] = 0;
          }
        } else {
          Dtype prob_a = prob_data[i * dim + label_value * inner_num_ + j];
          for (int c = 0; c < bottom[0]->shape(softmax_axis_); ++c) {
            if(c == label_value){
              Dtype diff_element = std::pow((1 - prob_a), gamma_);
              Dtype diff_element_mutal = gamma_ *
                                       prob_a*log(std::max(prob_a,Dtype(FLT_MIN))) + prob_a -1;
              focaldiff = diff_element * diff_element_mutal*alpha_;
            }else{
              Dtype pc = prob_data[i * dim + c * inner_num_ + j];
              Dtype diff_element = std::pow((1 - prob_a), gamma_ -1)*pc;
              Dtype diff_element_mutal =  1 - prob_a - gamma_ *
                                       prob_a*log(std::max(prob_a,Dtype(FLT_MIN)));
              focaldiff = diff_element * diff_element_mutal*alpha_;
            }
            bottom_diff[i * dim + c * inner_num_ + j] = focaldiff;
          }        
          ++count;
        }
      }
    }
    // Scale gradient
    Dtype normalizer = LossLayer<Dtype>::GetNormalizer(
        normalization_, outer_num_, inner_num_, count);
    Dtype loss_weight = top[0]->cpu_diff()[0] / normalizer;
    caffe_scal(prob_.count(), loss_weight, bottom_diff);
  }
}

#ifdef CPU_ONLY
STUB_GPU(focalSoftmaxWithLossLayer);
#endif

INSTANTIATE_CLASS(focalSoftmaxWithLossLayer);
REGISTER_LAYER_CLASS(focalSoftmaxWithLoss);

}  // namespace caffe
